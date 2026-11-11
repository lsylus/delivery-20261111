import {build} from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const id='@qmh/dsh-satellite-heater-drawing';
await fs.mkdir(path.join(root,'lib'),{recursive:true});
await build({entryPoints:[path.join(root,'src/client.jsx')],outfile:path.join(root,'lib/client.js'),bundle:true,
  format:'cjs',platform:'browser',target:'es2022',external:['react'],
  banner:{js:`window.__ModuleLoader__.load({id:${JSON.stringify(id)},factory:(require)=>{var module={exports:{}};var exports=module.exports;`},
  footer:{js:'return module.exports;}});'}});
await fs.mkdir(path.join(root,'public'),{recursive:true});
for(const name of ['index.html','app.js','app.css'])await fs.copyFile(path.join(root,'../web',name),path.join(root,'public',name));
for(const name of ['pdf.mjs','pdf.worker.mjs'])await fs.copyFile(path.join(root,'node_modules/pdfjs-dist/build',name),path.join(root,'public',name));
await fs.copyFile(path.join(root,'node_modules/pdfjs-dist/LICENSE'),path.join(root,'public/PDFJS-LICENSE.txt'));
await import('./check-package.mjs');
