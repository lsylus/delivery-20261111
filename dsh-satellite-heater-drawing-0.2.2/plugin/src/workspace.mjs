export const workspaceEntry = Object.freeze({
  id: 'custom-heater-drawing', plugin: 'custom-heater-drawing', key: 'heater-drawing',
  name: {zh: '矩形加热器出图', en: 'Heater drawings'}, order: 33, defaultVisible: true,
});
export function registerWorkspace(ctx) {
  return ctx.inject(['agentWorkspaces'], scope => scope.effect(() => scope.agentWorkspaces.register(workspaceEntry)));
}
