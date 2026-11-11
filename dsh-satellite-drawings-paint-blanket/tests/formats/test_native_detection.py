from pathlib import Path
import pytest
from thermal_drawings.importers.detect import detect


@pytest.mark.parametrize('name,body,format_,version', [
    ('板.prt.5', b'#UGC:2 PART 2063\n#Creo TM 9.0 All Rights Reserved. 9.0.8.0\n', 'Creo_PART', '9.0.8.0'),
    ('sub.ASM.12', b'#UGC:2 ASSEMBLY 2063\n#Creo TM 9.0 All Rights Reserved. 9.0.8.0\n', 'Creo_ASSEMBLY', '9.0.8.0'),
    ('old.prt.1', b'#UGC:2 PART 2063\n', 'Creo_PART', None),
    ('nx.prt', b'SPLMSSTR\x00\x00UG_PART\x00', 'NX_PART', None),
    ('probe.prt', b'', 'unknown', None),
    ('fake.prt.5', b'arbitrary file', 'unknown', None),
    ('fake.asm', b'section .text\nglobal asm_call\n', 'unknown', None),
    ('part.asm.3', b'#UGC:2 PART 2063\n', 'unknown', None),
    ('asm.prt.3', b'#UGC:2 ASSEMBLY 2063\n', 'unknown', None),
    ('nx.prt.5', b'SPLMSSTR\x00UG_PART', 'unknown', None),
    ('part.bin', b'#UGC:2 PART 2063\n', 'unknown', None),
    ('not-nx.prt', b'UG_PART', 'unknown', None),
    ('spoof.prt', b'ISO-10303-21;\nHEADER;', 'STEP', None),
])
def test_content_and_suffix_are_not_native_success(tmp_path, name, body, format_, version):
    path = tmp_path / name
    path.write_bytes(body)
    result = detect(path)
    assert result['detected_format'] == format_
    assert result['vendor_version'] == version
    assert result['geometry_verified'] is False


def test_revision_is_not_vendor_release(tmp_path):
    path = tmp_path / 'x.prt.40'
    path.write_bytes(b'#UGC:2 PART 2063\n#Creo TM 9.0 9.0.8.0\n')
    result = detect(path)
    assert result['save_revision'] == 40
    assert result['vendor_version'] == '9.0.8.0'
