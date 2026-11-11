import {build} from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export async function buildWeb(module) {
  const web=path.join(root,`plugins/${module}/web`);
  await fs.mkdir(path.join(web,'dist'),{recursive:true});
  await build({entryPoints:[path.join(web,'src/main.tsx')],outfile:path.join(web,'dist/app.js'),bundle:true,format:'esm',platform:'browser',target:'es2022',minify:true});
  await fs.copyFile(path.join(web,'index.html'),path.join(web,'dist/index.html'));
  await fs.cp(path.join(web,'demo'),path.join(web,'dist/demo'),{recursive:true});
}
export async function buildPlugin(module) {
  await buildWeb(module);
  const p=path.join(root,`plugins/${module}/plugin`);
  await build({entryPoints:[path.join(p,'src/index.mjs')],outfile:path.join(p,'lib/index.mjs'),bundle:true,format:'esm',platform:'node',target:'node22'});
  await build({entryPoints:[path.join(root,'packages/host-bridge/src/mcp.mjs')],outfile:path.join(p,'lib/mcp.mjs'),bundle:true,format:'esm',platform:'node',target:'node22'});
  await build({entryPoints:[path.join(root,'packages/host-bridge/src/mcp-context.mjs')],outfile:path.join(p,'lib/mcp-context.mjs'),bundle:true,format:'esm',platform:'node',target:'node22'});
  const client=await build({entryPoints:[path.join(p,'src/client.jsx')],bundle:true,write:false,format:'cjs',platform:'browser',external:['react'],target:'es2022'});
  await fs.writeFile(path.join(p,'lib/client.js'),`window.__ModuleLoader__.load({id:"@satellite-drawings/${module}-plugin",factory:(require)=>{var module={exports:{}};var exports=module.exports;\n${client.outputFiles[0].text}\nreturn module.exports;}});\n`);
  await fs.cp(path.join(root,`plugins/${module}/web/dist`),path.join(p,'public'),{recursive:true});
}
if(process.argv[1]===fileURLToPath(import.meta.url)) await buildWeb(process.argv[2]);
