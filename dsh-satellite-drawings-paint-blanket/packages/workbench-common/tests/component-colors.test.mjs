import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';

const output=await build({
 entryPoints:[fileURLToPath(new URL('../src/component-colors.ts',import.meta.url))],
 bundle:true,
 platform:'node',
 format:'esm',
 target:'es2022',
 write:false,
});
const {componentColors}=await import('data:text/javascript;base64,'+Buffer.from(output.outputFiles[0].contents).toString('base64'));
const n=(instance_id,parent_instance_id)=>({instance_id,parent_instance_id});

test('a single solid receives one stable component color',()=>{
 const first=componentColors([n('motor',null)],['motor']);
 const second=componentColors([n('motor',null)],['motor']);
 assert.equal(first.get('motor'),second.get('motor'));
});

test('top-level components receive distinct colors',()=>{
 const instances=[n('root',null),n('assembly','root'),n('a','assembly'),n('b','assembly'),n('c','assembly')];
 const colors=componentColors(instances,['a','b','c']);
 assert.equal(new Set(colors.values()).size,3);
});

test('all physical descendants of one top-level component share a color',()=>{
 const instances=[n('root',null),n('assembly','root'),n('module-a','assembly'),n('sub-a','module-a'),n('leaf-a1','sub-a'),n('leaf-a2','module-a'),n('module-b','assembly'),n('leaf-b','module-b')];
 const colors=componentColors(instances,['leaf-a1','leaf-a2','leaf-b']);
 assert.equal(colors.get('leaf-a1'),colors.get('leaf-a2'));
 assert.notEqual(colors.get('leaf-a1'),colors.get('leaf-b'));
});

test('single-child wrappers do not create artificial color groups',()=>{
 const instances=[n('root',null),n('wrapper','root'),n('module','wrapper'),n('leaf','module')];
 assert.equal(componentColors(instances,['leaf']).size,1);
});

test('separate roots retain independent component colors',()=>{
 const colors=componentColors([n('a',null),n('b',null)],['a','b']);
 assert.notEqual(colors.get('a'),colors.get('b'));
});
