import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';

const archive=process.argv[2];if(!archive)throw Error('archive required');
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'heater-client-check-'));
execFileSync('tar',['-xzf',path.resolve(archive),'-C',directory]);
const require=createRequire(new URL('../plugin/package.json',import.meta.url));
let client;const opened=[];
vm.runInNewContext(fs.readFileSync(path.join(directory,'package/lib/client.js'),'utf8'),{
  window:{open:(...args)=>opened.push(args),__ModuleLoader__:{load(entry){
    assert.equal(entry.id,'@qmh/dsh-satellite-heater-drawing');client=entry.factory(require);
  }}},
});
assert.deepEqual(Array.from(client.inject),['slots','sidebarRight','sidebarRightTabs']);
const slots=[];
let definition;
const ctx={effect:setup=>setup(),sidebarRightTabs:{register(value){definition=value;return ()=>{};}},sidebarRight:{openTabIn:(...args)=>opened.push(args)}};
client.apply({...ctx,slots:{inject(_name,callback){callback();},register(entry,component){slots.push({entry,component});}}});
assert.equal(slots.length,4);
assert.equal(definition.kind,'heater-drawing');assert.equal(definition.keepMounted,true);
assert.equal(definition.guide[0].title(),'矩形加热器出图');
const sidebar=slots.find(x=>x.entry.name==='sidebar.right.pane.tab');
assert.equal(sidebar.entry.key,definition.id);
const nav=slots.find(x=>x.entry.name==='custom.agent.nav');
const workspace=slots.find(x=>x.entry.name==='custom.agent.workspace');
assert.equal(workspace.entry.key,'heater-drawing');
assert.equal(nav.entry.metadata.id,'custom-heater-drawing');
let selected;nav.component({activeTab:'other',onSelectTab:key=>{selected=key;}}).props.onClick();assert.equal(selected,'heater-drawing');
for(const session of ['sessionA','sessionB']){
  const panel=workspace.component({sessionId:session});
  const frame=panel.props.children.find(x=>x?.type==='iframe');
  assert.equal(frame.props.src,'/satellite-heater/?session='+session);assert.equal(frame.key,session);
}
const empty=workspace.component({});assert.equal(empty.props.children.some(x=>x?.type==='iframe'),false);
const action=slots.find(x=>x.entry.name==='conversation.session.header.actions');
assert.equal(action.entry.id,'heater-drawing-open');
for(const session of ['sessionA','sessionB','session &中文/#']){
  const button=action.component({sessionId:session,...action.entry.inject()});assert.equal(button.type,'button');assert.equal(button.props.disabled,false);
  assert.equal(button.props.children.trim(),'矩形加热器出图');button.props.onClick();
  assert.deepEqual(opened.at(-1),[session,'heater-drawing']);
  const panel=sidebar.component({sessionId:session});const frame=panel.props.children.find(x=>x?.type==='iframe');
  assert.equal(frame.props.src,'/satellite-heater/?session='+encodeURIComponent(session));
}
const count=opened.length;
for(const sessionId of [undefined,null,'']){const button=action.component({sessionId,...action.entry.inject()});assert.equal(button.props.disabled,true);button.props.onClick();}
assert.equal(opened.length,count);
const fallback=[];
client.apply({...ctx,slots:{inject(name,callback){if(['conversation.session.header.actions','sidebar.right.pane.tab'].includes(name))callback();},register(entry,component){fallback.push({entry,component});}}});
assert.equal(fallback.length,2);assert.ok(fallback.some(x=>x.entry.id==='heater-drawing-open'));
console.log('PASS: extracted client loader, native sidebar type/body/guide, header opens owning session, original optional workspace, encoding and no-session guard');
