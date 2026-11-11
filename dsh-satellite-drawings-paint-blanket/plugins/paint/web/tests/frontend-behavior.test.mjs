import assert from 'node:assert/strict';
import test from 'node:test';
import {batchDiagnosticSummary} from '../src/batch-diagnostics.ts';
import {PROTECTION_RENDER_ORDER,selectionOverlayPresentation} from '../../../../packages/workbench-common/src/selection-overlay.ts';

const ref=(instance_id,entity_id='face-1')=>({instance_id,entity_id});

test('selected face overlay remains visible through occluding parts without taking the protection layer',()=>{
 const selected=selectionOverlayPresentation(false);
 assert.equal(selected.material.depthTest,false);
 assert.equal(selected.material.depthWrite,false);
 assert.equal(selected.material.transparent,true);
 assert.ok(selected.material.opacity>0&&selected.material.opacity<1);
 assert.ok(selected.renderOrder<PROTECTION_RENDER_ORDER);
});

test('batch diagnostic compacts penetration and budget evidence with affected objects',()=>{
 const group={status:'needs_review',instance_name:'Walls_part',direction_label:'-Y',target_face_refs:[ref('wall')],paint:{drawing_document:null,diagnostics:[
  {code:'penetration',status:'fail',source_refs:[ref('wall'),ref('bracket-a')],observed:{volume_mm3:12}},
  {code:'penetration',status:'fail',source_refs:[ref('wall'),ref('bracket-b')],observed:{volume_mm3:8}},
  {code:'budget_exhausted',status:'needs_review',source_refs:[ref('wall')],observed:{message:'maximum_pairs=10000'}},
 ]}};
 const summary=batchDiagnosticSummary(group);
 assert.deepEqual(summary.codes,[{code:'penetration',count:2},{code:'budget_exhausted',count:1}]);
 assert.deepEqual(summary.objects,['Walls_part / face-1','bracket-a / face-1','bracket-b / face-1']);
 assert.match(summary.hints.join(' '),/截面轮廓外扩 3 mm/);
 assert.match(summary.hints.join(' '),/扫描规模超限/);
 assert.equal(summary.detail,'maximum_pairs=10000');
});

test('batch diagnostic gives actionable footprint and topology guidance',()=>{
 const footprint=batchDiagnosticSummary({status:'failed',target_face_refs:[ref('wall')],error:{code:'native_footprint_common',message:'intersection failed'}});
 const topology=batchDiagnosticSummary({status:'failed',target_face_refs:[ref('wall')],error:{code:'invalid_brep',message:'invalid topology'}});
 assert.match(footprint.hints[0],/投影足迹拓扑/);
 assert.match(topology.hints[0],/STEP 拓扑/);
});
