"""Start a persistent, private loopback trial with one packaged plugin."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def wait_file(path, process, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with {process.returncode}; see trial logs")
        if path.exists():
            return json.loads(path.read_text())
        time.sleep(.1)
    raise TimeoutError(str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=ROOT/'work/simple-v1-trial')
    parser.add_argument('--port', type=int, default=18890)
    parser.add_argument('--module', choices=('paint','blanket'), default='blanket')
    parser.add_argument('--converter-config', type=Path)
    parser.add_argument('--background', action='store_true', help='Start a detached persistent trial')
    parser.add_argument('--stop', action='store_true', help='Stop only the recorded trial launcher')
    args = parser.parse_args()
    os.umask(0o077)
    state = args.state_dir.resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    launcher_file=state/'launcher.json'
    if args.stop:
        if not launcher_file.exists():
            raise RuntimeError('No recorded launcher for this trial')
        launcher=json.loads(launcher_file.read_text());pid=launcher['pid']
        cmdline=Path(f'/proc/{pid}/cmdline')
        if cmdline.exists():
            command=cmdline.read_bytes().replace(b'\x00',b' ').decode()
            if str(Path(__file__).resolve()) not in command or str(state) not in command:
                raise RuntimeError('Recorded PID no longer belongs to this trial')
            os.kill(pid,signal.SIGTERM)
        launcher_file.unlink()
        return
    if args.background:
        if launcher_file.exists():
            old=json.loads(launcher_file.read_text())
            if Path(f'/proc/{old["pid"]}/cmdline').exists():
                raise RuntimeError('Trial launcher is already running')
        command=[sys.executable,str(Path(__file__).resolve()),'--state-dir',str(state),'--port',str(args.port),'--module',args.module]
        if args.converter_config:command+=['--converter-config',str(args.converter_config.resolve())]
        (state/'session.json').unlink(missing_ok=True)
        with (state/'launcher.log').open('a') as launcher_log:
            process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=launcher_log,stderr=subprocess.STDOUT,start_new_session=True)
        launcher_file.write_text(json.dumps({'pid':process.pid,'state_dir':str(state)}))
        session=wait_file(state/'session.json',process,60)
        print('SIMPLE_TRIAL_READY '+session['origin'])
        return
    private = state/'private.json'
    if private.exists():
        identity = json.loads(private.read_text())
    else:
        identity = {'token': secrets.token_urlsafe(32), 'cookie': secrets.token_urlsafe(32)}
        private.write_text(json.dumps(identity));private.chmod(0o600)
    credentials = state/'credentials.json'
    credentials.write_text(json.dumps({hashlib.sha256(identity['token'].encode()).hexdigest(): {
        'owner': 'qmh', 'session': 'simple-'+args.module, 'module': args.module}}))
    credentials.chmod(0o600)
    upload_limit = 1024*1024*1024
    backend_config = {'data_root': str(state/'data'), 'credentials_file': str(credentials),
                      'auth_mode': 'dev-only', 'upload_limit': upload_limit,
                      'timeout_s': 900, 'memory_limit_mb': 32768}
    if args.converter_config:
        backend_config['converter_config'] = str(args.converter_config.resolve())
    config = state/'backend.json';config.write_text(json.dumps(backend_config))
    ready = state/'backend-ready.json';ready.unlink(missing_ok=True)
    host_ready = state/'host-ready.json';host_ready.unlink(missing_ok=True)
    bundled_node = ROOT/'.tools/node/bin/node'
    node = str(bundled_node) if bundled_node.is_file() else shutil.which('node')
    if not node:
        raise RuntimeError('Node.js 22.19 or newer is required')
    subprocess.run([str(ROOT/'node_modules/esbuild/bin/esbuild'), str(ROOT/'scripts/simple_host.tsx'),
                    '--bundle', '--platform=browser', '--target=es2022', f'--outfile={state/"host.js"}'], check=True)
    backend = host = None
    logs = []
    try:
        backend_log = (state/'backend.log').open('a');logs.append(backend_log)
        backend = subprocess.Popen([sys.executable, str(ROOT/'scripts/serve_dev.py'), '--config', str(config), '--ready-file', str(ready)],
                                   cwd=ROOT, stdout=backend_log, stderr=subprocess.STDOUT)
        backend_info = wait_file(ready, backend)
        service_url = f'http://127.0.0.1:{backend_info["port"]}'
        deadline = time.monotonic()+15
        while True:
            try:
                request = urllib.request.Request(service_url+'/api/v1/health', headers={'Authorization': 'Bearer '+identity['token']})
                with urllib.request.urlopen(request, timeout=2) as response:
                    assert response.status == 200
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(.1)
        host_config = state/'host.json'
        host_config.write_text(json.dumps({'serviceUrl': service_url, 'port': args.port, 'module': args.module,
            'pluginRoot': str(ROOT/'plugins'/args.module/'plugin'), 'hostBundle': str(state/'host.js'),
            'ready': str(host_ready), 'cookie': identity['cookie'], 'uploadLimitBytes': upload_limit,
            'identity': {'owner_id':'qmh','session_id':'simple-'+args.module,'module':args.module,'backendCredential':identity['token']}}))
        host_log = (state/'host.log').open('a');logs.append(host_log)
        host = subprocess.Popen([node, str(ROOT/'scripts/simple_host.mjs'), str(host_config)], cwd=ROOT,
                                stdout=host_log, stderr=subprocess.STDOUT)
        host_info = wait_file(host_ready, host)
        session = dict(origin=host_info['origin'], cookie=identity['cookie'], backend_port=backend_info['port'],
                       backend_pid=backend.pid,host_pid=host.pid, state_dir=str(state),
                       fixtures=str(ROOT/'fixtures/synthetic'/('paint' if args.module=='paint' else 'simple-v1')),
                       satellite_step=str(ROOT/'fixtures/release-cases/simplified.step'))
        (state/'session.json').write_text(json.dumps(session));(state/'session.json').chmod(0o600)
        print('SIMPLE_TRIAL_READY '+host_info['origin'],flush=True)
        done = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: done.set())
        signal.signal(signal.SIGINT, lambda *_: done.set())
        while not done.wait(1):
            if backend.poll() is not None or host.poll() is not None:
                raise RuntimeError('Trial process exited; see logs')
    finally:
        for process in (host,backend):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=20)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
        (state/'session.json').unlink(missing_ok=True)


if __name__=='__main__':
    main()
