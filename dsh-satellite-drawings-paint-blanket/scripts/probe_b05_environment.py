"""Bounded read-only tool discovery. Do not read secrets or contact old service jobs."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from thermal_drawings.importers.manifest import sha

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent


def main():
    commands = [
        ['uname', '-sm'],
        ['docker', 'ps', '--format', '{{.Names}} {{.Image}}'],
        ['find', '/opt', '/usr/local', '/data/qmh', '-maxdepth', '4', '-iname', '*creo*',
         '-o', '-iname', '*hoops*', '-o', '-iname', '*cadex*', '-o', '-iname', '*exchanger*'],
    ]
    records = []
    for argv in commands:
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            out = p.stdout
            if argv[0] == 'docker':
                out = '\n'.join(line for line in out.splitlines() if any(x in line.lower() for x in ['cad', 'creo', 'nx']))
            records.append(dict(argv=argv, exit_code=p.returncode, stdout=out, stderr=p.stderr))
        except (OSError, subprocess.TimeoutExpired) as exc:
            records.append(dict(argv=argv, exit_code=124, error=type(exc).__name__))
    prefix = BASE / 'dsh-satellite-geometry/runtime/tianyuan-geometry-20261008'
    historical = []
    for relative in ['creo-step-export/conversion-brief.md',
                     'conversion-test/Star1_sample_report.json',
                     'conversion-test/Star1_assembly_report.json',
                     'convert_creo_with_nx.py']:
        path = prefix / relative
        row = dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size, historical_only=True)
        if path.suffix == '.json':
            old = json.loads(path.read_text(encoding='utf-8-sig'))
            row.update({k:old.get(k) for k in ['translator','status','nxFileExists','rootBodyCount']})
        historical.append(row)
    nx_root = BASE / 'dsh-satellite-thermal/runtime/nx-jobs/9c766c672f60488b81ea902fc92e700e/nx'
    nx_report = nx_root / 'model-report.json'
    nx = json.loads(nx_report.read_text())
    result = dict(status='pass', scope='bounded environment discovery, not native capability acceptance',
        python=platform.python_version(), platform=platform.platform(), commands=records,
        executables={n:shutil.which(n) for n in ['parametric','creo','xtop','ugraf','run_journal','CADExchangerCLI','ExchangerConv','wine','freecadcmd']},
        license_variable_presence={n:n in os.environ for n in ['PTC_D_LICENSE_FILE','LM_LICENSE_FILE','SPLM_LICENSE_SERVER','NX_JOURNAL_EXECUTABLE']},
        config_present=(ROOT/'work/config/converters.local.json').is_file(),
        license_state='unverified', selected_adapter=None,
        historical_evidence=historical,
        historic_workstation='D:/Desktop and D:/Install/NX12 references are from another Windows workstation; not a configured execution endpoint here',
        nx_business_candidate=dict(path=str(nx_report),sha256=sha(nx_report),bytes=nx_report.stat().st_size,
            mesh=nx.get('mesh'), qualification='historical STEP-derived thermal business geometry; not external native assembly acceptance'),
        limitations=['No exhaustive scan of unrelated users or remote hosts',
                     'FreeCAD/OCCT and existing thermal STEP-to-NX worker do not establish a licensed Creo 9 reader',
                     'No credentials requested/read; no license checkout, old worker job, global setup or CAD process started'])
    out = ROOT/'docs/evidence/B05/environment.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status='pass',native_adapter=None,license_state='unverified')))


if __name__ == '__main__':
    main()
