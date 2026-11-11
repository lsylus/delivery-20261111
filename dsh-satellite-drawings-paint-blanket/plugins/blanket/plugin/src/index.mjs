import {fileURLToPath} from 'node:url';
import {applyPlugin} from '../../../../packages/host-bridge/src/plugin.mjs';
export const name='satellite-blanket';
export const inject=['webServer','connection','sessions','credentials','tools'];
export async function apply(ctx,config={}){return applyPlugin(ctx,config,'blanket',fileURLToPath(new URL('../public/',import.meta.url)));}
