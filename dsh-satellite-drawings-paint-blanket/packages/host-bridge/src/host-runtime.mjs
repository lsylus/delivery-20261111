import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
export async function loadHostModule(ctx, specifier) {
  const anchor = ctx.get?.('profileContext')?.installAnchor;
  if (!anchor) throw new Error('host_install_anchor_unavailable');
  return import(pathToFileURL(createRequire(anchor).resolve(specifier)).href);
}
export const modules = Object.freeze(['paint', 'blanket']);
export function workspaceEntry(module) {
  if (!modules.includes(module)) throw new Error('invalid_module');
  return {id:`custom-satellite-${module}`, plugin:`custom-satellite-${module}`,
    key:`satellite-${module}`, name:{zh:module==='paint'?'喷漆图纸':'多层图纸',en:module==='paint'?'Paint drawings':'Blanket drawings'},
    order:module==='paint'?31:32, defaultVisible:true};
}
export function registerWorkspace(ctx,module) {
  return ctx.inject(['agentWorkspaces'], scope=>scope.effect(()=>scope.agentWorkspaces.register(workspaceEntry(module))));
}
