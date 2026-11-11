"""DSH account Host signatures plus live, signed per-request authorization callbacks."""
import base64
import hashlib
import http.client
import ipaddress
import json
import re
import time
import threading
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from .auth import Principal
from ..domain.errors import ServiceError, require

def decode(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid encoding')
    raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    if base64.urlsafe_b64encode(raw).decode().rstrip('=') != value:
        raise ValueError('Noncanonical encoding')
    return raw


class HostAuthenticator:
    def __init__(self, settings):
        self.registry = settings.host_registry
        self.seen = {}
        self.lock = threading.Lock()

    def authenticate(self, request, body):
        try:
            if (not ipaddress.ip_address(request.client.host).is_loopback or
                    request.url.hostname not in ('127.0.0.1', '::1', 'localhost') or
                    request.headers.get('origin') or request.headers.get('authorization')):
                raise ServiceError(403, 'host_transport_required', 'Private Host transport required')
            header = request.headers.get('x-drawings-host', '')
            if len(header) > 8192:
                raise ValueError('Assertion too large')
            payload, signature = header.split('.')
            claims = json.loads(decode(payload))
            expected = {'v','kid','tenant','user','home_hash','module','session','method','path','body_sha256','headers','nonce','expires','callback_port'}
            if set(claims) != expected or claims['v'] != 1:
                raise ValueError('Invalid assertion')
            st = self.registry.stat()
            if self.registry.is_symlink() or st.st_mode & 0o077:
                raise ValueError('Private registry required')
            registry = json.loads(self.registry.read_text())
            row = registry['keys'].get(claims['kid'])
            if not row or row.get('enabled') is not True or any(row.get(k) != claims[k] for k in ('tenant','user','home_hash','module')):
                raise ValueError('Unenrolled or revoked Host')
            public = decode(row['public_key'])
            if hashlib.sha256(public).hexdigest() != claims['kid']:
                raise ValueError('Key id mismatch')
            key = load_der_public_key(public)
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError('Wrong key type')
            key.verify(decode(signature), payload.encode())
            now = int(time.time() * 1000)
            if (type(claims['expires']) is not int or not now < claims['expires'] <= now + 15000 or
                    not re.fullmatch(r'[A-Za-z0-9_-]{43}', claims['nonce']) or
                    not re.fullmatch(r'[A-Za-z0-9._-]{1,160}', claims['session']) or
                    claims['module'] not in ('paint','blanket') or
                    claims['method'] != request.method or claims['path'] != request.url.path or request.url.query or
                    claims['body_sha256'] != hashlib.sha256(body).hexdigest() or
                    claims['headers'] != {k:request.headers[k] for k in ('content-type','x-filename') if k in request.headers}):
                raise ValueError('Request assertion mismatch')
            port = claims['callback_port']
            if type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError('Invalid callback')
            with self.lock:
                self.seen = {k:v for k,v in self.seen.items() if v > now}
                if claims['nonce'] in self.seen or len(self.seen) >= 4096:
                    raise ValueError('Replayed assertion or capacity exceeded')
                self.seen[claims['nonce']] = claims['expires']
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
            try:
                conn.request('POST', '/b07/authorize', json.dumps({'nonce':claims['nonce']}), {'Content-Type':'application/json'})
                response = conn.getresponse()
                raw = response.read(4097)
                if response.status != 200 or len(raw)>4096:
                    raise ValueError('Callback denied')
                result = json.loads(raw)
                key.verify(decode(result['signature']), result['payload'].encode())
                if json.loads(decode(result['payload'])) != {'nonce':claims['nonce'],'active':True}:
                    raise ValueError('Host session no longer authorized')
            finally:
                conn.close()
            if int(time.time()*1000) >= claims['expires']:
                raise ValueError('Authorization expired')
            current = json.loads(self.registry.read_text())['keys'].get(claims['kid'])
            if current != row:
                raise ValueError('Host enrollment changed during authorization')
            # Account owner is registry-controlled, never supplied as an HTTP identity claim.
            owner = hashlib.sha256((row['tenant']+'\0'+row['user']).encode()).hexdigest()
            return Principal(owner, claims['session'], row['module'])
        except ServiceError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, OSError, InvalidSignature, http.client.HTTPException):
            raise ServiceError(401, 'host_unauthenticated', 'Host authorization unavailable, expired or revoked') from None


def authorize_resource(repo, principal, method, path):
    """New drawings projects have owner-only membership; optional ACL can reduce rights."""
    parts = path.split('/')[3:]
    require(parts and parts[0] in ('health','capabilities','projects','sessions','runs','artifacts'),404)
    if parts[0] in ('health','capabilities'):
        return
    if parts[0]=='sessions':
        require(len(parts)==3 and parts[1]==principal.session and parts[2]=='binding',403,'session_forbidden')
        return  # Binding payload membership checked by Repository.binding and host middleware.
    if parts==['projects']:
        require(method=='POST',405)
        return
    require(len(parts)>=2,404)
    with repo.tx() as c:
        if parts[0]=='runs':
            row=c.execute('SELECT project,module FROM runs WHERE id=?',(parts[1],)).fetchone()
            require(row is not None and row['module']==principal.module,404)
            project=row['project']
        elif parts[0]=='artifacts':
            row=c.execute('SELECT project,module,shared FROM artifacts WHERE id=?',(parts[1],)).fetchone()
            require(row is not None and (row['shared'] or row['module']==principal.module),404)
            project=row['project']
        else:
            project=parts[1]
        repo.project(c,principal,project)
        row=c.execute('SELECT can_read,can_write FROM host_project_access WHERE project=? AND owner=?',(project,principal.owner)).fetchone()
        require(row is None or bool(row['can_read']) and (method=='GET' or bool(row['can_write'])),403,'project_access_denied')
        # Reading project metadata permits explicit same-owner session binding; all data requires binding.
        if not (parts[0]=='projects' and len(parts)==2 and method=='GET'):
            repo.bound(c,principal,project)
