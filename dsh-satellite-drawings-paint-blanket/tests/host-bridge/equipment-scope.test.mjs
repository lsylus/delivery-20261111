import test from 'node:test';
import assert from 'node:assert/strict';
import {equipmentScope,parentEquipmentScope} from '../../plugins/blanket/web/src/simpleSelection.ts';
const n=(instance_id,parent_instance_id,name)=>({instance_id,parent_instance_id,name});
const snapshot={instances:[n('sat',null,'Satellite'),n('panel','sat','设备面板'),n('motor','panel','Motor'),n('body','motor','Body'),n('term','motor','Terminal'),n('pin','term','Pin'),n('bolt','motor','Bolt'),n('other','panel','Camera'),n('motor2','panel','Motor'),n('body2','motor2','Body'),n('pin2','motor2','Pin')]};
const physical=['body','pin','bolt','other','body2','pin2'];
test('one click on motor body includes attached descendants and excludes neighbouring equipment',()=>{
 const scope=equipmentScope(snapshot,physical,'body');assert.deepEqual(scope.instanceIds,['body','pin','bolt']);assert.equal(scope.moduleId,'motor');assert.equal(scope.name,'Motor');assert.equal(scope.grouped,true);
});
test('same product instances retain independent placed selection scopes',()=>{
 assert.deepEqual(equipmentScope(snapshot,physical,'body2').instanceIds,['body2','pin2']);
});
test('explicit expansion can select a named parent but never the satellite root',()=>{
 const parent=parentEquipmentScope(snapshot,physical,'motor');assert.equal(parent.moduleId,'panel');assert.deepEqual(parent.instanceIds,physical);assert.equal(parentEquipmentScope(snapshot,physical,'panel'),null);
});
test('flat and generic assemblies do not guess engineering membership',()=>{
 const flat={instances:[n('sat',null,'Satellite'),n('a','sat','Motor'),n('b','sat','Screw')]};assert.deepEqual(equipmentScope(flat,['a','b'],'a').instanceIds,['a']);
 const generic={instances:[n('root',null,'Assembly'),n('group','root','20261010_asm_5_asm'),n('a','group','Body'),n('b','group','Screw')]};assert.deepEqual(equipmentScope(generic,['a','b'],'a').instanceIds,['a']);
});
test('native leaves without rendered triangles remain part of selected module',()=>{
 assert.ok(equipmentScope(snapshot,['body','pin','bolt'],'body').instanceIds.includes('pin'));
});
test('technical escape names decode and do not collapse Chinese equipment labels',()=>{
 const s={instances:[n('sat',null,'Assembly'),n('m','sat','_X2_7535673A_X0_'),n('a','m','Body'),n('b','m','Pin')]};assert.equal(equipmentScope(s,['a','b'],'a').name,'电机');
});
test('unknown identities and cyclic source scope fail closed',()=>{
 assert.throws(()=>equipmentScope(snapshot,physical,'unknown'),/失效/);
 const s={instances:[n('root',null,'Assembly'),n('a','b','Body'),n('b','a','Terminal')]};assert.throws(()=>equipmentScope(s,['a'],'a'),/循环/);
});
