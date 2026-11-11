"""Start an explicitly configured development service on an ephemeral loopback port."""
import argparse
import json
import os
from pathlib import Path
import socket
import uvicorn
from thermal_drawings.app import create_app
from thermal_drawings.settings import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--ready-file', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    settings = Settings.from_file(args.config)
    app = create_app(settings)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((settings.bind_host, 0))
    sock.listen(128)
    ready = Path(args.ready_file)
    ready.write_text(json.dumps({'host': settings.bind_host, 'port': sock.getsockname()[1], 'pid': os.getpid()}))
    try:
        uvicorn.Server(uvicorn.Config(app, host=settings.bind_host, log_level='warning', proxy_headers=False, access_log=False)).run(sockets=[sock])
    finally:
        ready.unlink(missing_ok=True)
        sock.close()


if __name__ == '__main__':
    main()
