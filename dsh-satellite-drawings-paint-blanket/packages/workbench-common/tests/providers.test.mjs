import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';

const output=await build({
  entryPoints:[fileURLToPath(new URL('../src/providers.ts',import.meta.url))],
  bundle:true,
  platform:'node',
  format:'esm',
  target:'es2022',
  write:false,
});
const providers=await import('data:text/javascript;base64,'+Buffer.from(output.outputFiles[0].contents).toString('base64'));
const model={project_id:'project',model_id:'model',model_revision:1,assembly_digest:'a'.repeat(64)};

test('paint provider reuses recommendations across engineering revisions of the same model',()=>{
  const recommendations={revision_id:'old-revision',model_ref:model,groups:[]};
  assert.equal(providers.paintRecommendationsForRevision({recommendations},{id:'new-revision',model_ref:model}),recommendations);
});

test('paint provider rejects recommendations from a different model',()=>{
  const recommendations={revision_id:'old-revision',model_ref:model,groups:[]};
  const revision={id:'new-revision',model_ref:{...model,model_revision:2}};
  assert.throws(()=>providers.paintRecommendationsForRevision({recommendations},revision),/推荐结果版本冲突/);
});

test('upload filenames are UTF-8 percent encoded before entering request headers',()=>{
  assert.equal(providers.encodeUploadFilename('简化卫星.step'),'%E7%AE%80%E5%8C%96%E5%8D%AB%E6%98%9F.step');
  assert.equal(providers.encodeUploadFilename('simplified.step'),'simplified.step');
});
