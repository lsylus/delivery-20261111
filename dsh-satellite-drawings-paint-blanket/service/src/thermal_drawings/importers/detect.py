"""Content detection only: a recognizable header is not a geometry/load certificate."""
from pathlib import Path
import re

NATIVE_NAME = re.compile(r'^(.+)\.(prt|asm)(?:\.(\d+))?$', re.I)


def detect(path):
    path = Path(path)
    with path.open('rb') as stream:
        head = stream.read(8192)
    name = NATIVE_NAME.fullmatch(path.name)
    result = dict(detected_format='unknown', vendor=None, vendor_version=None,
                  save_revision=int(name[3]) if name and name[3] else None,
                  kind=None, geometry_verified=False, reason='unrecognized content')
    match = re.match(rb'#UGC:2 (PART|ASSEMBLY)\s', head)
    if match:
        kind = match[1].decode()
        suffix = 'prt' if kind == 'PART' else 'asm'
        if not name or name[2].lower() != suffix:
            result['reason'] = 'Creo header and native filename disagree'
            return result
        versions = re.findall(rb'#Creo[^\r\n]*?([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s*(?:\r?\n|$)', head)
        result.update(detected_format='Creo_' + kind, vendor='PTC Creo', kind=kind,
                      vendor_version=versions[-1].decode() if versions else None,
                      reason='UGC header and filename agree; native load remains unverified')
    elif head.startswith(b'SPLMSSTR') and b'UG_PART' in head:
        if name and name[2].lower() == 'prt' and name[3] is None:
            result.update(detected_format='NX_PART', vendor='Siemens NX', kind='PART',
                          reason='NX signature; version, geometry and assembly dependencies unknown')
        else:
            result['reason'] = 'NX content and filename disagree'
    elif head.lstrip().startswith(b'ISO-10303-21;'):
        result.update(detected_format='STEP', reason='STEP envelope header; reader still required')
    elif path.suffix.lower() == '.asm' and re.search(
            rb'(?im)^\s*(?:section\s|segment\s|\.text\b|global\s|bits\s|;)', head):
        result['reason'] = 'assembly language text, not CAD'
    return result


def reference_hints(path):
    """Untrusted plaintext hints, never an authoritative proprietary dependency parser.

    Binary record prefixes/history can contaminate names; even a resolved hint
    is not proof of an active component, unit, occurrence or latest version.
    """
    raw = Path(path).read_bytes()
    text = raw.decode('utf-8', errors='replace')
    return sorted(set(re.findall(r'[\w.\-]{1,120}\.(?:prt|asm)(?:\.\d+)?', text, re.I)), key=str.casefold)
