import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
process.chdir(fileURLToPath(new URL('../',import.meta.url)));
const name=process.argv[2];
await build({absWorkingDir:process.cwd(),entryPoints:[name==='host-bridge'?'packages/host-bridge/src/plugin.mjs':'packages/workbench-common/src/Workbench.tsx'],outfile:`packages/${name}/dist/index.js`,bundle:true,platform:name==='host-bridge'?'node':'browser',format:'esm',target:'es2022'});
