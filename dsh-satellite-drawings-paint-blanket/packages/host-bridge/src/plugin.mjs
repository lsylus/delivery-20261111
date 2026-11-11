import {registerHost} from './host-proxy.mjs';
import {registerWorkspace} from './host-runtime.mjs';
import {createProxy,staticHandler} from './proxy.mjs';
export function applyPlugin(ctx,config,module,publicRoot) {
  registerWorkspace(ctx,module);
  const identity=ctx.get?.('satelliteDrawingsIsolatedIdentity');
  if(!identity)return registerHost(ctx,config,module,publicRoot);
  const proxy=createProxy({module,serviceUrl:config.serviceUrl||'http://127.0.0.1:1',origin:config.origin||'http://127.0.0.1:1',resolveIdentity:identity?.resolve?.bind(identity),uploadLimitBytes:config.uploadLimitBytes,requestTimeoutMs:config.requestTimeoutMs});
  ctx.effect(()=>ctx.webServer.register({kind:'prefix',path:`/api/satellite-${module}`,handler:proxy}));
  ctx.effect(()=>ctx.webServer.register({kind:'prefix',path:`/satellite-${module}`,handler:staticHandler(publicRoot,`/satellite-${module}`)}));
}
