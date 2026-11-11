export function workspaceEntry(module) {
  if(!['paint','blanket'].includes(module))throw Error('invalid_module');
  return {id:`custom-satellite-${module}`,plugin:`custom-satellite-${module}`,key:`satellite-${module}`,name:{zh:module==='paint'?'喷漆图纸':'多层图纸',en:module==='paint'?'Paint drawings':'Blanket drawings'},order:module==='paint'?31:32,defaultVisible:true};
}
