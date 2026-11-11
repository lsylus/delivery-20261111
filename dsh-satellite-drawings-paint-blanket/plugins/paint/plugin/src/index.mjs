import {fileURLToPath} from 'node:url';
import {applyPlugin} from '../../../../packages/host-bridge/src/plugin.mjs';
export const name='satellite-paint';
export const inject=['webServer','connection','sessions','credentials','tools'];
export async function apply(ctx,config={}){return applyPlugin(ctx,config,'paint',fileURLToPath(new URL('../public/',import.meta.url)));}
