import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const required=['src/index.mjs','lib/client.js','public/index.html','public/app.js','public/app.css','public/pdf.mjs','public/pdf.worker.mjs','public/PDFJS-LICENSE.txt',
 'runtime/bootstrap.py','runtime/files.json','runtime/requirements.txt','runtime/service/src/heater_drawing/app/server.py',
 'runtime/templates/heater-a4-v1/template.dxf','runtime/schemas/revision.schema.json','README.md','cordis.patch.yml'];
for(const name of required)if(!(await fs.stat(path.join(root,name))).isFile())throw Error('missing_release_file: '+name);
const manifest=JSON.parse(await fs.readFile(path.join(root,'runtime/files.json'),'utf8'));
for(const [name,sha] of Object.entries(manifest)){
 const file=path.resolve(root,'runtime',name);
 if(!file.startsWith(path.join(root,'runtime')+path.sep))throw Error('invalid_runtime_path');
 if(createHash('sha256').update(await fs.readFile(file)).digest('hex')!==sha)throw Error('stale_runtime_file: '+name);
}
if(!Object.keys(manifest).some(p=>p.startsWith('wheels/')))throw Error('offline_wheels_missing');
console.log('Plugin release files and offline runtime hashes verified');
