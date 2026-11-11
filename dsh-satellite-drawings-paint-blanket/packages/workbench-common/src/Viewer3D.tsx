import {mappedGeometry} from './SurfaceGeometry';
import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {blanketOverlay} from './BlanketOverlay';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {resolveFace} from '../../host-bridge/src/selection-context.mjs';
import {PROTECTION_RENDER_ORDER,selectionOverlayPresentation} from './selection-overlay';
import {componentColors} from './component-colors';
export function Viewer3D({loaded,selected,onSelect,onError,selectedInstances=[],excludedInstances=[],installationFace=null,faceStates={}}:{loaded:any;selected:any[];onSelect:Function;onError:Function;selectedInstances?:string[];excludedInstances?:string[];installationFace?:any;faceStates?:Record<string,{state:string;selectable?:boolean}>}){
  const mount=useRef<HTMLDivElement>(null),live=useRef({selected,onSelect,selectedInstances,excludedInstances,installationFace,faceStates}),[ready,setReady]=useState(false);
  live.current={selected,onSelect,selectedInstances,excludedInstances,installationFace,faceStates};
  useEffect(()=>{
    let alive=true,raf=0,renderer:THREE.WebGLRenderer|undefined,controls:OrbitControls|undefined,scene:THREE.Scene|undefined;
    const el=mount.current!;setReady(false);
    const dispose=()=>{cancelAnimationFrame(raf);controls?.dispose();scene?.traverse((o:any)=>{o.geometry?.dispose();if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach((m:any)=>m.dispose());});renderer?.dispose();renderer?.domElement.remove();};
    (async()=>{
      const gltf=await new GLTFLoader().parseAsync(loaded.glb.slice(0),'');if(!alive)return;
      scene=new THREE.Scene();scene.background=new THREE.Color('#eef3f7');scene.add(gltf.scene);
      const meshes:any[]=[],faceMapping=new Map<string,any[]>();
      for(const face of loaded.map.faces){const key=`${face.node}|${face.mesh}|${face.primitive}`,entries=faceMapping.get(key)||[];entries.push(face);faceMapping.set(key,entries);}
      gltf.scene.traverse((o:any)=>{
        if(!o.isMesh)return;
        const a=gltf.parser.associations.get(o) as {nodes?:number;meshes?:number;primitives?:number}|undefined;let parent:any=o,node=a?.nodes;
        while(node===undefined&&parent){node=gltf.parser.associations.get(parent)?.nodes;parent=parent.parent;}
        if(node===undefined||a?.meshes===undefined||a?.primitives===undefined)throw Error('缺少 GLB primitive 映射');
        o.userData.pick={node,mesh:a.meshes,primitive:a.primitives};
        const ranges=faceMapping.get(`${node}|${a.meshes}|${a.primitives}`)||[],mapped=ranges.find(face=>face.triangle_start===0&&face.triangle_count>0);
        if(!mapped)throw Error('缺少 GLB 面映射');o.userData.faceRef=mapped.face_ref;o.userData.pickFaces=ranges;
        const old=o.material;o.material=new THREE.MeshStandardMaterial({color:'#7095b5',metalness:.08,roughness:.65,side:THREE.DoubleSide});(Array.isArray(old)?old:[old]).forEach((m:any)=>m.dispose());meshes.push(o);
      });
      const baseColors=componentColors(loaded.snapshot.instances,meshes.map(o=>o.userData.faceRef.instance_id));
      for(const r of loaded.paint?.regions||[]){
        const shape=new THREE.Shape(r.loops[0].points.map((p:number[])=>new THREE.Vector2(p[0],p[1])));
        for(const hole of r.loops.slice(1))shape.holes.push(new THREE.Path(hole.points.map((p:number[])=>new THREE.Vector2(p[0],p[1]))));
        const geom=mappedGeometry(shape,r.local_frame,r.surface_mapping);
        const mesh=new THREE.Mesh(geom,new THREE.MeshBasicMaterial({color:r.id===loaded.selectedRegion?'#f97316':'#eab95b',transparent:true,opacity:.8,side:THREE.DoubleSide,polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2}));mesh.renderOrder=PROTECTION_RENDER_ORDER;scene.add(mesh);
      }
      if(loaded.blanketResult)scene.add(blanketOverlay(loaded));
      const isolationInstances=new Set<string>(loaded.isolationInstances||[]),isolating=isolationInstances.size>0;
      const visibleMeshes=meshes.filter(o=>!isolating||isolationInstances.has(o.userData.faceRef.instance_id));
      const visibleMeshSet=new Set(visibleMeshes);for(const o of meshes)o.visible=visibleMeshSet.has(o);
      const framedMeshes=visibleMeshes.length?visibleMeshes:meshes,box=new THREE.Box3();
      for(const o of framedMeshes){o.updateWorldMatrix(true,false);box.expandByObject(o,true);}
      const center=box.getCenter(new THREE.Vector3()),size=Math.max(box.getSize(new THREE.Vector3()).length(),.001);
      if(loaded.installationPreview){const frame=loaded.installationPreview,toGL=(p:number[])=>new THREE.Vector3(p[0]/1000,p[2]/1000,-p[1]/1000),origin=toGL(frame.origin);for(const [axis,color] of [[frame.x_axis,0xef4444],[frame.y_axis,0x22c55e],[frame.z_axis,0x2563eb]] as [number[],number][]){const direction=new THREE.Vector3(axis[0],axis[2],-axis[1]);scene.add(new THREE.ArrowHelper(direction,origin,size*.22,color,size*.04,size*.025));}}
      const camera=new THREE.PerspectiveCamera(38,1,Math.max(size/1000,.00001),Math.max(size*100,10));camera.position.copy(center).add(new THREE.Vector3(size*.9,size*.8,size*1.2));
      scene.add(new THREE.HemisphereLight(0xffffff,0x718096,2.5));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(1,2,3);scene.add(light);
      renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));el.appendChild(renderer.domElement);renderer.domElement.setAttribute('aria-label','真实模型三维视图');
      controls=new OrbitControls(camera,renderer.domElement);controls.target.copy(center);controls.update();
      let down=[0,0];renderer.domElement.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY];});
      renderer.domElement.addEventListener('pointerup',e=>{
        if(Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
        const rect=renderer!.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);
        const hit=ray.intersectObjects(visibleMeshes,false)[0];if(!hit)return;
        try{const ref=resolveFace({...loaded.map,faces:hit.object.userData.pickFaces},loaded.revision.model_ref,loaded.hash,{...hit.object.userData.pick,triangle:hit.faceIndex});
          if(live.current.faceStates[ref.instance_id+'|'+ref.entity_id]?.selectable===false)return;
          // GLB world is metres/Y-up; report source world millimetres/Z-up.
          live.current.onSelect([ref],'3d',[[hit.point.x*1000,-hit.point.z*1000,hit.point.y*1000]],camera.matrixWorldInverse.toArray().reduce((out:number[],_,i:number,a:number[])=>{out.push(a[(i%4)*4+Math.floor(i/4)]);return out;},[]));
        }catch(err){onError(String(err));}
      });
      let highlightedSelected:any[]|null=null,highlightedInstallation:string|null=null,highlightedStates:any=null;const rangeOverlays:THREE.Mesh[]=[];
      const draw=()=>{if(!alive)return;const w=el.clientWidth,h=el.clientHeight;renderer!.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
        const active=live.current,targets=new Set(active.selectedInstances),excluded=new Set(active.excludedInstances),faces=new Set(active.selected.map(r=>r.instance_id+'|'+r.entity_id));
        const installationKey=active.installationFace?active.installationFace.instance_id+'|'+active.installationFace.entity_id:null;
        if(highlightedSelected!==active.selected||highlightedInstallation!==installationKey||highlightedStates!==active.faceStates){
          for(const overlay of rangeOverlays){overlay.removeFromParent();overlay.geometry.dispose();(overlay.material as THREE.Material).dispose();}rangeOverlays.length=0;
          for(const o of meshes){for(const range of o.userData.pickFaces){const ref=range.face_ref,key=ref.instance_id+'|'+ref.entity_id;if(!faces.has(key)&&key!==installationKey)continue;
            const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',o.geometry.getAttribute('position'));if(o.geometry.index)geometry.setIndex(o.geometry.index);geometry.setDrawRange(range.triangle_start*3,range.triangle_count*3);
            const presentation=selectionOverlayPresentation(key===installationKey),overlay=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({...presentation.material,side:THREE.DoubleSide,polygonOffset:true,polygonOffsetFactor:-3,polygonOffsetUnits:-3}));overlay.renderOrder=presentation.renderOrder;overlay.raycast=()=>{};o.add(overlay);rangeOverlays.push(overlay);
          }}highlightedSelected=active.selected;highlightedInstallation=installationKey;highlightedStates=active.faceStates;
        }
        for(const o of meshes){const ref=o.userData.faceRef,key=ref.instance_id+'|'+ref.entity_id,state=active.faceStates[key]?.state;let color=baseColors.get(ref.instance_id)||'#7095b5';if(targets.has(ref.instance_id))color='#22a880';if(excluded.has(ref.instance_id))color='#bc66d8';if(o.userData.pickFaces.length===1){if(faces.has(key))color='#16a34a';if(state==='invalid')color='#dc2626';if(installationKey===key)color='#06b6d4';}o.material.color.set(color);}
        renderer!.render(scene!,camera);raf=requestAnimationFrame(draw);};draw();setReady(true);
    })().catch(e=>{if(alive)onError(String(e));});
    return()=>{alive=false;dispose();};
  },[loaded]);
  return <div className="viewer" data-testid="viewer" data-ready={ready} ref={mount}/>;
}
