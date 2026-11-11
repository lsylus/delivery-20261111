"""Run only the new account-authenticated backend; no legacy services or dev fallback."""
import argparse
import json
import os
import socket
from pathlib import Path
import uvicorn
from thermal_drawings.settings import Settings
from thermal_drawings.app import create_app

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--ready-file',type=Path,required=True);p.add_argument('--port',type=int,default=18777);args=p.parse_args()
    os.umask(0o077)
    settings=Settings.from_file(args.config)
    if settings.auth_mode!='dsh-account':raise ValueError('Host service requires dsh-account mode')
    app=create_app(settings);sock=socket.socket();sock.bind(('127.0.0.1',args.port));sock.listen(128)
    args.ready_file.write_text(json.dumps({'host':'127.0.0.1','port':sock.getsockname()[1],'pid':os.getpid(),'auth_mode':'dsh-account'})+'\n')
    try:uvicorn.Server(uvicorn.Config(app,log_level='warning',access_log=False,proxy_headers=False)).run(sockets=[sock])
    finally:args.ready_file.unlink(missing_ok=True);sock.close()

if __name__=='__main__':main()
