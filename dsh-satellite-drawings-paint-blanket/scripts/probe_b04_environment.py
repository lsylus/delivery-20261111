"""Read-only, bounded tool discovery and runtime evidence for B04."""
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
from thermal_drawings.drawing.validation import file_record

ROOT = Path(__file__).resolve().parents[1]


def main():
    commands = []
    for argv in [
        ['uname','-sm'],
        ['getconf','GNU_LIBC_VERSION'],
        ['dpkg-query','-W','xvfb','freecad','librecad'],
        ['find','/opt','/usr/local','/data/qmh','-maxdepth','6','-type','f','(',
         '-iname','*ODA*Converter*','-o','-iname','*Teigha*Converter*','-o','-iname','acad.exe',
         '-o','-iname','accoreconsole*',')','-print'],
        ['fc-match','Droid Sans Fallback'],
    ]:
        result = subprocess.run(argv,capture_output=True,text=True,timeout=60)
        commands.append({'argv':argv,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    evidence = ROOT/'docs/evidence/B04'
    evidence.mkdir(exist_ok=True,parents=True)
    discovery = {'status':'recorded','commands':commands,
                 'path_lookup':{name:shutil.which(name) for name in ('ODAFileConverter','xvfb-run','Xvfb','freecad','acad','accoreconsole','dwgread')},
                 'limits':'Scoped discovery, not an exhaustive machine inventory. Private B04 ODA is configured separately.',
                 'alternative_CAD':'FreeCAD 0.19.2 installed; actual importDWG uses ODA. See alternative-cad.json for real edit/save/reopen attempt and failures. LibreCAD was not found by dpkg-query.'}
    (evidence/'tool-discovery.json').write_text(json.dumps(discovery,indent=2)+'\n')
    environment = {'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),
                   'libraries':{name:importlib.metadata.version(name) for name in ('ezdxf','shapely','jsonschema','pytest')},
                   'font':file_record('/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'),
                   'production_services_started':False,'source_repositories':'read-only G/T/S/H',
                   'autocad':'No authorized AutoCAD environment provided; Windows PATH/uninstall registry/common install roots inspected with no AutoCAD entry.'}
    (evidence/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    print(json.dumps(environment))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
