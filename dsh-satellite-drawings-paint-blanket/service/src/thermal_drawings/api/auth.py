"""Only operator-provisioned opaque development credentials; no client identity claims."""
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import secrets
from ..domain.errors import ServiceError


@dataclass(frozen=True)
class Principal:
    owner: str
    session: str
    module: str


class DevAuthenticator:
    def __init__(self, settings):
        self.identities = json.loads(settings.credentials_file.read_text())
        if not self.identities:
            raise ValueError('At least one explicit dev credential required')
        for digest, value in self.identities.items():
            if len(digest) != 64 or set(value) != {'owner', 'session', 'module'} or value['module'] not in ('paint', 'blanket') or not all(value.values()):
                raise ValueError('Invalid operator credential mapping')

    def authenticate(self, request):
        try:
            peer = ipaddress.ip_address(request.client.host)
            host = request.headers.get('host', '').split(':')[0]
            loopback_host = host == 'localhost' or ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback_host = False
            peer = None
        if peer is None or not peer.is_loopback or not loopback_host or request.headers.get('origin'):
            raise ServiceError(403, 'dev_only', 'Development credentials require a loopback server-to-server connection')
        header = request.headers.get('authorization', '')
        if not header.startswith('Bearer '):
            raise ServiceError(401, 'unauthenticated', 'Authentication required')
        digest = hashlib.sha256(header[7:].encode()).hexdigest()
        for expected, value in self.identities.items():
            if secrets.compare_digest(digest, expected):
                return Principal(**value)
        raise ServiceError(401, 'unauthenticated', 'Invalid credential')
