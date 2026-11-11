import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const host='/data/lbk/codex_web/deepseek-harness2';
const repo='/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing';
const archive=repo+'/dist/plugin-release-20261110/qmh-dsh-satellite-heater-drawing-0.2.1.tgz';
const sourcePaths={
  declaration:'packages/client/ui-conversation/src/client/apply.ts',
  outlet:'packages/client/ui-conversation/src/client/skeleton/ConversationSession.tsx',
  session:'packages/client/ui-session/src/client/index.ts',
  injection:'packages/client/ui-renderer/src/client/registry.ts',
  core:'packages/client/ui-slots/lib/index.js',
};
const sources=Object.fromEntries(Object.entries(sourcePaths).map(([key,rel])=>[key,fs.readFileSync(path.join(host,rel),'utf8')]));
const slot='conversation.session.header.actions';
const declaration=sources.declaration.match(/'conversation\.session\.header\.actions':\s*\{\s*kind:\s*'([^']+)',\s*scope:\s*'([^']+)'\s*\}/);
assert.ok(declaration);
assert.equal(declaration[1],'list');assert.equal(declaration[2],'session');
assert.ok(sources.outlet.includes("renderSlot('conversation.session.header.actions', {})"));
assert.ok(sources.session.includes('props: { sessionId: binding.sessionId }'));
assert.ok(sources.session.includes("installScope('session', service.adapter)"));
assert.ok(sources.injection.includes('if (spec === undefined) return'));

const {SlotCore}=await import(pathToFileURL(path.join(host,sourcePaths.core)));
const core=new SlotCore();
const opened=[];
const require=createRequire(path.join(repo,'plugin/package.json'));
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'heater-current-host-'));
let client;
try {
  execFileSync('tar',['-xzf',archive,'-C',temp,'package/lib/client.js']);
  vm.runInNewContext(fs.readFileSync(path.join(temp,'package/lib/client.js'),'utf8'),{
    window:{open:(...args)=>opened.push(args),__ModuleLoader__:{load(entry){client=entry.factory(require);}}},
  });
  // Only the slot ledger is the actual host implementation. This thin adapter
  // models inject's declaration waiting, without claiming a live Cordis mount.
  const waits=[];
  client.apply({slots:{
    inject(name,callback){waits.push({name,callback,dispose:undefined});},
    register(options,component){return core.register(options,component);},
  }});
  assert.equal(waits.length,3);
  const frame=core.register({name:'root',children:{[slot]:{kind:declaration[1],scope:declaration[2]}}},()=>null);
  for(const wait of waits)if(core.specDynamic(wait.name))wait.dispose=wait.callback();
  assert.equal(core.specDynamic('custom.agent.nav'),undefined);
  assert.equal(core.specDynamic('custom.agent.workspace'),undefined);
  const entries=core.entries(slot);
  assert.equal(entries.length,1);
  for(const sessionId of ['sessionA','sessionB','session &中文/#']){
    const button=entries[0].component({sessionId});
    assert.equal(button.props.disabled,false);
    button.props.onClick();
    assert.deepEqual(opened.at(-1),['/satellite-heater/?session='+encodeURIComponent(sessionId),'_blank','noopener,noreferrer']);
  }
  const before=opened.length;
  const disabled=entries[0].component({});
  assert.equal(disabled.props.disabled,true);disabled.props.onClick();assert.equal(opened.length,before);
  frame();assert.equal(core.entries(slot).length,0);
  for(const wait of waits)wait.dispose?.();
  const sha256=value=>createHash('sha256').update(value).digest('hex');
  const evidence={
    target_dsh:'0.2.2-rc.1-102617d-dirty',
    host_checkout:fs.realpathSync(host),
    host_head:execFileSync('git',['-c','safe.directory='+fs.realpathSync(host),'-C',host,'rev-parse','--short=7','HEAD'],{encoding:'utf8'}).trim(),
    basis:'Current working-tree source plus actual built SlotCore; older geometry/thermal plugins not used',
    source_sha256:Object.fromEntries(Object.entries(sourcePaths).map(([key,rel])=>[rel,sha256(sources[key])])),
    archive,archive_sha256:sha256(fs.readFileSync(archive)),
    checks:['current host declares list/session header action slot','current header renders action outlet','current session scope publishes sessionId','current inject waits for absent declarations','packaged client registers with real current-host SlotCore without custom.agent declarations','button URL tracks supplied current session and encodes special characters','missing-session guard','real slot ledger removes entry when parent is disposed'],
    status:'passed',
    limits:'SlotCore integration and source contract checks; inject adapter and session binding are fixtures. Live authenticated DSH installation and UI not tested. Dirty working-tree source is not a pristine commit snapshot.',
  };
  fs.writeFileSync(repo+'/docs/evidence/header-button-021/current-host-contract.json',JSON.stringify(evidence,null,2)+'\n');
  console.log(JSON.stringify(evidence,null,2));
} finally {
  fs.rmSync(temp,{recursive:true,force:true});
}
