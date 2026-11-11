import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {build} from 'esbuild';

const temporary=await fs.mkdtemp(path.join(os.tmpdir(),'satellite-client-'));
const output=path.join(temporary,'client.mjs');
await build({
  entryPoints:[new URL('../src/client.jsx',import.meta.url).pathname],
  outfile:output,
  bundle:true,
  format:'esm',
  platform:'node',
  target:'node22',
});
const {clientPlugin}=await import(output);

test.after(()=>fs.rm(temporary,{recursive:true,force:true}));

for(const module of ['paint','blanket'])test(`${module} exposes workspace and right-sidebar entries`,()=>{
  const registrations=[];
  const tabTypes=[];
  const opened=[];
  const ctx={
    effect(activate){return activate();},
    sidebarRightTabs:{register(definition){tabTypes.push(definition);return()=>{};}},
    sidebarRight:{openTabIn(...args){opened.push(args);}},
    slots:{
      inject(_name,activate){return activate();},
      register(definition,component){registrations.push({definition,component});return()=>{};},
    },
  };
  const plugin=clientPlugin(module);
  assert.deepEqual(plugin.inject,['slots','sidebarRight','sidebarRightTabs']);
  plugin.apply(ctx);
  const entryKey=`satellite-${module}`;
  const sidebarId=`@satellite-drawings/${module}-plugin/workspace`;
  assert.equal(tabTypes[0].id,sidebarId);
  assert.equal(tabTypes[0].kind,entryKey);
  assert(registrations.some(({definition})=>definition.name==='custom.agent.nav'));
  assert(registrations.some(({definition})=>definition.name==='custom.agent.workspace'&&definition.key===entryKey));
  assert(registrations.some(({definition})=>definition.name==='sidebar.right.pane.tab'&&definition.key===sidebarId));
  const header=registrations.find(({definition})=>definition.name==='conversation.session.header.actions');
  assert.equal(header.definition.id,`satellite-${module}-open`);
  const button=header.component({sessionId:'session-1',...header.definition.inject()});
  button.props.onClick();
  assert.deepEqual(opened,[['session-1',entryKey]]);
});
