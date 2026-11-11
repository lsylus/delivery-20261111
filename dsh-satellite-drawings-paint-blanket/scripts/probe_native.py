"""B05 real source probe. Exit 3 means native acceptance is blocked, not passed."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from thermal_drawings.importers.manifest import (
    inventory, candidate_bundle, copy_candidate, verify_manifest, file_record, sha)
from thermal_drawings.importers.native import NativeConverter, NativeConversionUnavailable

ROOT = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def run_bounded(argv, log, timeout=120):
    """Own a new process group; kill and reap it on timeout or interruption."""
    with Path(log).open('wb') as stream:
        process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return 124
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise


def load_native_config(path):
    raw = json.loads(Path(path).read_text()) if Path(path).is_file() else {}
    if not isinstance(raw, dict):
        raise ValueError('unsupported converter configuration')
    config = raw.get('native', raw)
    allowed = {'adapter', 'license_state', 'supported_versions', 'endpoint_or_executable',
               'vendors', 'timeout_s', 'credential_ref'}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError('unsupported converter configuration; no arbitrary executable commands allowed')
    # Endpoint/credential fields remain private and are not executed or copied to evidence.
    return {k:v for k,v in config.items() if k in {'adapter','license_state','supported_versions'}}


def probe(case_manifest, config_path, output):
    specification = json.loads(Path(case_manifest).read_text())
    output = Path(output).resolve()
    for case in specification['cases']:
        if output.is_relative_to(Path(case['source_root']).resolve()):
            raise ValueError('output inside source root is prohibited')
    config_exists = Path(config_path).is_file()
    config = load_native_config(config_path)
    output.mkdir(parents=True, exist_ok=True)
    result = dict(status='blocked', config_file_present=config_exists,
                  config_state='unvalidated_adapter' if config.get('adapter') else 'not_configured',
                  cases=[], resources_created=[], resources_cleaned=[], conversions_executed=0,
                  native_acceptance=dict(real_creo_part='blocked', complete_creo_assembly='blocked'),
                  limitations=['No selected licensed native adapter; actual dependencies, units, geometry and transforms remain unverified'])
    indices = {}
    scratch_parent = ROOT / 'work/runs'
    scratch_parent.mkdir(parents=True, exist_ok=True)
    for case in specification['cases']:
        case_id = case['id']
        if not case_id.replace('-', '').isalnum():
            raise ValueError('invalid case ID')
        source = Path(case['source_root']).resolve(strict=True)
        key = str(source)
        if key not in indices:
            indices[key] = inventory(source)
            # Full provenance/inventory, not a purported dependency closure.
            dump(output / f'{case["inventory_id"]}-inventory.json', indices[key])
        bundle = candidate_bundle(indices[key], case['main_file'], case_id)
        dump(output / 'cases' / f'{case_id}.json', bundle)
        with tempfile.TemporaryDirectory(prefix='b05-', dir=scratch_parent) as scratch:
            result['resources_created'].append(scratch)
            copied = copy_candidate(bundle, Path(scratch) / 'input')
            manifest = bundle['source_manifest']
            converter = NativeConverter(config)
            try:
                converter.convert(manifest, copied)
            except NativeConversionUnavailable as exc:
                capability = exc.capability
            else:
                raise RuntimeError('No selected native engine may claim success')
            verify_manifest(source, manifest)
            verify_manifest(copied, manifest)
            result['cases'].append(dict(id=case_id, required=case['required'],
                role=case['role'], status='blocked', capability=capability,
                manifest_ref=f'cases/{case_id}.json', manifest_sha256=sha(output / 'cases' / f'{case_id}.json'),
                assembly_digest=manifest['assembly_digest'], copied_files=len(manifest['files']),
                copied_bytes=sum(f['bytes'] for f in manifest['files']),
                source_unchanged=True, geometry=bundle['geometry'],
                dependency_status='unverified', native_process_exit=None, step_asset=None))
        result['resources_cleaned'].append(scratch)
    # Historic suspect STEP: validate an isolated copy with B02, never repurpose it as converted output.
    historical = specification['historical_step']
    source = Path(historical['source_root'])
    record = file_record(source, historical['relative_path'])
    with tempfile.TemporaryDirectory(prefix='b05-readback-', dir=scratch_parent) as scratch:
        import shutil
        result['resources_created'].append(scratch)
        step = Path(scratch) / 'historical.step'
        shutil.copyfile(source / historical['relative_path'], step)
        assert sha(step) == record['sha256']
        target = Path(scratch) / 'readback.json'
        argv = [sys.executable, str(ROOT / 'scripts/readback_native_step.py'), str(step), str(target)]
        code = run_bounded(argv, output / 'historical-readback.log')
        readback = json.loads(target.read_text()) if target.is_file() else dict(status='failed', reason='No readback evidence')
        # Timeout/error cannot be hidden by an output file written before termination.
        if code != 0:
            readback['status'] = 'failed'
        result['historical_step'] = dict(input=record, source_root=str(source), command=argv,
            exit_code=code, readback=readback, native_conversion_evidence=False)
        assert file_record(source, historical['relative_path']) == record
    result['resources_cleaned'].append(scratch)
    # Rehash entire inventoried source sets to cover ignored runtime assets as well.
    for key, original in indices.items():
        assert inventory(Path(key)) == original, 'source inventory changed during probe'
    result['all_source_inventories_unchanged'] = True
    dump(output / 'conversion-report.json', result)
    dump(output / 'capabilities.json', dict(status='blocked', platform=sys.platform,
        selected_adapter=None, advertised_supported_formats=[], validated_case_ids=[],
        formats=[dict(case_id=c['id'], **c['capability']) for c in result['cases']],
        recovery='Provide an authorized Creo 9.0.8.0-compatible workstation/SDK and a documented execution/loader API; then implement one adapter and run real part plus full assembly acceptance'))
    print(json.dumps(dict(status='blocked', cases=len(result['cases']), conversions_executed=0,
                          historical_step_exit=code, sources_unchanged=True)))
    return 3


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case-manifest', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    return probe(a.case_manifest, a.config, a.output)


if __name__ == '__main__':
    raise SystemExit(main())
