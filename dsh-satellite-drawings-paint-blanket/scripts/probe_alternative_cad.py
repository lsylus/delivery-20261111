"""Record an actual isolated FreeCAD attempt; never supplies AutoCAD approval."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

from thermal_drawings.drawing.validation import file_record

ROOT=Path(__file__).resolve().parents[1]


def run_probe(root=ROOT, timeout_s=60):
    root=Path(root).resolve()
    work=Path(tempfile.mkdtemp(prefix='freecad-b04-',dir=root/'work'))
    evidence=root/'docs/evidence/B04/alternative-cad-r1'/work.name
    input_file=evidence/'input.dwg'
    source=root/'docs/evidence/B04/sample.dwg'
    report={'status':'blocked','autocad_acceptance':False,'commands':[],
            'resources_created':[str(work)],'resources_cleaned':[],
            'scope':'Alternative CAD experiment; ODA-backed import/export is not independent native DWG verification'}
    try:
        evidence.mkdir(parents=True,exist_ok=True)
        _attempt(root, work, evidence, input_file, source, report, timeout_s)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report.update(status='failed',reason=str(exc))
    finally:
        # Only this invocation's mkdtemp directory; archived evidence is separate.
        shutil.rmtree(work)
        report['resources_cleaned'].append(str(work))
    (root/'docs/evidence/B04/alternative-cad-r1.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def _attempt(root, work, evidence, input_file, source, report, timeout_s):
    executable=shutil.which('freecadcmd')
    if executable and source.is_file():
        shutil.copyfile(source,input_file)
        config=json.loads((root/'work/config/converters.local.json').read_text())
        argv=['/usr/bin/xvfb-run','-a',executable,'--user-cfg',str(work/'user.cfg'),'--system-cfg',str(work/'system.cfg'),str(root/'scripts/freecad_b04_probe.py')]
        env={**os.environ,'B04_CAD_INPUT':str(input_file),'B04_CAD_OUTPUT':str(evidence),'B04_CAD_TEMP':str(work),
             'B04_ODA_EXECUTABLE':config['dwg']['executable'],'XDG_CONFIG_HOME':str(work/'config'),
             'XDG_CACHE_HOME':str(work/'cache'),'QT_QPA_PLATFORM':'xcb','TMPDIR':str(work)}
        log=evidence/'freecad-command.log'
        with log.open('w') as stream:
            process=subprocess.Popen(argv,cwd=work,env=env,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
            timed_out=False
            try:
                code=process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out=True;os.killpg(process.pid,signal.SIGKILL);code=process.wait()
            finally:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        report['commands'].append({'argv':argv,'exit_code':code,'timed_out':timed_out,'log_ref':str(log.relative_to(root))})
        result=evidence/'freecad-result.json'
        report['status']='attempted'
        report['result']=json.loads(result.read_text()) if result.is_file() else {'status':'failed','reason':'No FreeCAD result; see process log'}
        report['input']=file_record(input_file)
        report['artifacts']=[file_record(p) for p in sorted(evidence.iterdir()) if p.is_file()]
    else:
        report['reason']='FreeCAD executable or current real DWG missing'


def main():
    report=run_probe()
    print(json.dumps({'status':report['status'],'result':report.get('result',{}).get('status')}))
    # The attempt is evidence, not a required passing CAD gate.
    return 0


if __name__=='__main__':
    raise SystemExit(main())
