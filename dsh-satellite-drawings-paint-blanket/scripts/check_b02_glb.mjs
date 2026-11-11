import fs from 'node:fs';
import assert from 'node:assert/strict';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { Box3, Vector3, Raycaster } from 'three';
const root = 'docs/evidence/B02';
const path = root + '/artifacts/assembly-tree/model.glb';
const raw = fs.readFileSync(path);
const data = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
const gltf = await new GLTFLoader().parseAsync(data, '');
gltf.scene.updateMatrixWorld(true);
let triangles=0, primitives=0;
gltf.scene.traverse(o=>{
  if (o.isMesh) {
    primitives++;
    triangles += (o.geometry.index?.count ?? o.geometry.attributes.position.count)/3;
    assert(o.geometry.attributes.normal);
  }
});
assert.equal(primitives,19); assert.equal(triangles,38);
const box=new Box3().setFromObject(gltf.scene);
const expectedMin=[0,0,-.075], expectedMax=[.1,.04,0];
box.min.toArray().forEach((x,i)=>assert(Math.abs(x-expectedMin[i])<1e-8));
box.max.toArray().forEach((x,i)=>assert(Math.abs(x-expectedMax[i])<1e-8));
const hits=new Raycaster(new Vector3(.095,.1,-.06),new Vector3(0,-1,0)).intersectObject(gltf.scene,true);
assert(hits.length>0);
const map=JSON.parse(fs.readFileSync(root+'/artifacts/assembly-tree/mesh-map.json'));
const picks=hits.map(hit=>{
  const a=gltf.parser.associations.get(hit.object);
  let node=hit.object;
  while(node && gltf.parser.associations.get(node)?.nodes===undefined) node=node.parent;
  const nodeIndex=gltf.parser.associations.get(node).nodes;
  const entry=map.faces.find(e=>e.node===nodeIndex && e.mesh===a.meshes && e.primitive===a.primitives);
  assert(entry);assert(hit.faceIndex>=0 && hit.faceIndex<entry.triangle_count);
  return {node:nodeIndex,mesh:a.meshes,primitive:a.primitives,triangle:hit.faceIndex,instance_id:entry.face_ref.instance_id,entity_id:entry.face_ref.entity_id};
});
const evidence={status:'pass',loader:'Three.js GLTFLoader 0.184.0',primitives,triangles,world_units:'m/Y-up',bounds:{min:box.min.toArray(),max:box.max.toArray()},actual_ray_picks:picks};
fs.writeFileSync(root+'/glb-loader.json',JSON.stringify(evidence,null,2)+'\n');
console.log(JSON.stringify(evidence));
