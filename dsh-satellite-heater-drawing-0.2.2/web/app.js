const $=id=>document.getElementById(id);
const session=new URL(location.href).searchParams.get('session');
const base='/api/satellite-heater';
let current=null,selected=null,busy=false,poll=null,previewUrl=null,epoch=0;
let previewTask=null,previewDocument=null,previewRender=null,previewTurn=0,previewPage=1;
const states={validating:'正在校验 Excel 与图纸版面',resolving:'正在重新检查确认后的版面',awaiting_resolution:'需要处理输入或确认比例',ready:'校验通过，可以生成',queued:'已排队',running:'正在生成并核验 DWG／PDF',generated:'完整出图已生成',paused_error:'生成中断，可重试',failed:'后台处理失败',cancelled:'已取消'};
const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const active=x=>['validating','resolving','queued','running'].includes(x);
function notice(value){$('notice').textContent=value;$('notice').hidden=!value;}
async function request(route,options={}){
  const response=await fetch(base+route,{...options,cache:'no-store',headers:{'x-heater-session':session,...options.headers}});
  if(!response.ok){let value;try{value=await response.json();}catch{}throw Error(value?.error?.message||`请求失败（${response.status}）`);}
  return response;
}
async function json(route,body,headers){return (await request(route,body===undefined?{}:{method:'POST',body:JSON.stringify(body),headers:{'content-type':'application/json',...headers}})).json();}
function closePreview(){
  previewTurn++;if(previewRender)previewRender.cancel();previewRender=null;
  if(previewTask)previewTask.destroy().catch(()=>{});previewTask=null;previewDocument=null;
  if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;
  $('savePdf').removeAttribute('href');$('preview').width=0;$('preview').height=0;$('previewCard').hidden=true;
}
async function renderPdfPage(number){
  const doc=previewDocument,turn=previewTurn;if(!doc)return;
  $('previousPage').disabled=$('nextPage').disabled=true;$('previewStatus').textContent='正在显示图纸…';
  const page=await doc.getPage(number);if(turn!==previewTurn)return;
  const viewport=page.getViewport({scale:1.8}),canvas=$('preview');
  canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
  const task=page.render({canvasContext:canvas.getContext('2d'),viewport});previewRender=task;
  await task.promise;if(turn!==previewTurn)return;previewRender=null;previewPage=number;
  canvas.dataset.page=String(number);$('pageNumber').textContent=`第 ${number} / ${doc.numPages} 页`;
  $('previousPage').disabled=number===1;$('nextPage').disabled=number===doc.numPages;
  $('previewStatus').textContent='';
}
async function list(){
  const value=await json('/service/jobs');
  $('jobs').innerHTML=value.jobs.length?value.jobs.map(j=>`<button class="job ${selected===j.id?'active':''}" data-job="${escape(j.id)}">${escape(j.name)}<small>${escape(states[j.state]||j.state)}</small></button>`).join(''):'<p class="muted">本会话还没有任务。</p>';
  for(const button of $('jobs').querySelectorAll('[data-job]'))button.onclick=()=>load(button.dataset.job).catch(e=>notice(e.message));
}
async function load(id,quiet=false){
  const turn=quiet?epoch:++epoch;
  if(!quiet){selected=id;closePreview();notice('');}
  const value=await json('/service/jobs/'+id);
  if(turn!==epoch||selected!==id)return;
  const previousState=current?.id===id?current.state:null;
  current=value;render();
  clearTimeout(poll);poll=setTimeout(()=>load(id,true).catch(e=>{notice(e.message);$('connection').textContent='连接中断';}),active(value.state)?1800:10000);
  if(!quiet||previousState!==value.state)await list();
}
const rowTable=rows=>`<div class="scroll"><table><thead><tr><th>源行</th><th>代号</th><th>名称</th><th>比例</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${escape(r.row_id)}</td><td>${escape(r.code)}</td><td>${escape(r.name)}</td><td>${escape(r.scale)}</td></tr>`).join('')}</tbody></table></div>`;
function render(){
  const j=current,run=j.run;
  const review=run?.review?.status||'pending';
  const running=active(j.state);
  const issues=j.issues||[],proposals=j.proposals||[];
  const selectable=j.state==='awaiting_resolution'&&j.revision;
  $('detail').innerHTML=`<div class="bar"><h2>${escape(j.name)}</h2><span class="muted">${escape(j.id.slice(0,8))}</span></div>
    <p class="status ${j.state==='awaiting_resolution'||j.state==='paused_error'||j.state==='failed'?'warn':''}">${escape(states[j.state]||j.state)}${j.state==='generated'?' · '+(review==='approved'?'已记录工程复核通过':review==='rejected'?'工程复核未通过':'待工程复核'):''}</p>
    ${running?'<div class="progress" aria-label="处理中"></div><p class="muted">校验会检查所有行；生成会保存并重新打开 DWG，核验完整 PDF 集合。完成前不发布部分文件。</p>':''}
    <div class="stats"><div><strong>${j.total_rows??'—'}</strong><span>Excel 行数</span></div><div><strong>${j.skipped_rows?.length??0}</strong><span>明确跳过</span></div><div><strong>${j.expected_pages??'—'}</strong><span>预计图纸</span></div></div>
    ${j.requires_reupload?'<p class="status warn">请按下列问题修正 Excel 后重新上传。字段不完整或无效时，不生成替代数据。</p>':''}
    ${j.error||run?.error?`<p class="status warn">${escape(j.error?.message||run?.error?.message||'后台检查未通过，请检查字体／CAD 环境后重试。')}</p>`:''}
    ${issues.length?`<h3>需要检查的问题</h3><div class="scroll"><table><thead><tr><th>选择</th><th>源行／代号</th><th>字段</th><th>原因与修改建议</th></tr></thead><tbody>${issues.map(i=>`<tr><td>${selectable&&i.skippable&&i.scope==='row'?`<input type="checkbox" class="issue" aria-label="跳过 ${escape(i.row_id)}" value="${escape(i.issue_id)}" data-row="${escape(i.row_id)}">`:'—'}</td><td>${escape(i.sheet)}:${escape(i.excel_row)}<br>${escape(i.code)}</td><td>${escape(i.field)}</td><td>${escape(i.message)}<br><span class="muted">${escape(i.suggested_fix)}</span></td></tr>`).join('')}</tbody></table></div>${selectable?'<div class="actions"><button id="skip" class="danger">确认跳过选中问题的行</button></div>':''}`:''}
    ${proposals.length?`<h3>图纸超出当前比例的可用版面</h3><p class="muted">修改比例不改变模型实际尺寸。请逐项选择全部建议后一次确认；不接受的比例请修改 Excel 重传。</p><div class="scroll"><table><thead><tr><th>选择</th><th>源行</th><th>输入比例 → 建议</th><th>原因</th></tr></thead><tbody>${proposals.map(p=>`<tr><td><input type="checkbox" class="proposal" aria-label="接受 ${escape(p.row_id)} 比例" value="${escape(p.proposal_id)}" data-row="${escape(p.row_id)}"></td><td>${escape(p.row_id)}</td><td>${escape(p.original.label)} → ${escape(p.proposed.label)}</td><td>${escape(p.reason)}</td></tr>`).join('')}</tbody></table></div><div class="actions"><button id="scale">确认应用选中比例</button></div>`:''}
    ${j.rows?.length?'<h3>出图数据</h3>'+rowTable(j.rows):''}
    ${j.skipped_rows?.length?`<p class="status warn">本次不生成：${j.skipped_rows.map(escape).join('、')}。下载报告保留跳过记录。</p>`:''}
    <div class="actions">${j.exportable&&!running?`<button id="generate">${j.state==='generated'?'重新生成完整图纸':'生成 DWG 与 PDF'}</button>`:''}${['queued','running'].includes(j.state)?'<button id="cancel" class="danger">取消本次生成</button>':''}</div>
    ${run?.state==='generated'?`<h3>完整出图文件</h3><p class="muted">${review==='pending'?'以下为待复核图纸。':''}单页按 Excel 行顺序合并，完整包同时包含 DWG、PDF 和报告。</p><div id="downloads">${run.artifacts.filter(a=>['dwg','pdf_merged','pdf_single','zip','excel_actual'].includes(a.kind)).map(a=>`<button class="secondary download" data-artifact="${escape(a.id)}" data-filename="${escape(a.path.split('/').pop())}">${a.kind.startsWith('pdf')?'预览／下载 ':''}${escape(a.path.split('/').pop())}</button>`).join('')}</div><div class="actions"><button id="review" class="secondary">记录工程复核</button></div>`:''}`;
  if($('generate'))$('generate').onclick=()=>perform(async()=>{await json(`/service/jobs/${j.id}/runs`,{revision_hash:j.revision.revision_hash},{'idempotency-key':crypto.randomUUID()});await load(j.id);});
  if($('cancel'))$('cancel').onclick=()=>perform(async()=>{if(!confirm('取消本次生成？未完成的文件不会作为完整图纸发布。'))return;await json(`/service/jobs/${j.id}/runs/${run.id}/cancel`,{revision_hash:j.revision.revision_hash});await load(j.id);});
  if($('scale'))$('scale').onclick=()=>confirmDecision('scale');
  if($('skip'))$('skip').onclick=()=>confirmDecision('skip');
  if($('review'))$('review').onclick=()=>perform(async()=>{
    const approved=confirm('是否记录“工程复核通过”？选择“取消”可记录未通过。请实际审阅本次完整图纸后操作。');
    const comment=prompt(approved?'填写复核意见（通过）':'填写复核意见（未通过）');if(comment===null)return;
    await json('/confirm',{job_id:j.id,action:'review',revision_hash:j.revision.revision_hash,run_id:run.id,status:approved?'approved':'rejected',comment});await load(j.id);
  });
  for(const button of document.querySelectorAll('[data-artifact]'))button.onclick=()=>perform(()=>download(button.dataset.artifact,button.dataset.filename));
}
async function perform(operation){if(busy)return;busy=true;notice('');try{await operation();}catch(e){notice(e.message);}finally{busy=false;}}
async function confirmDecision(kind){return perform(async()=>{
  const j=current,boxes=[...document.querySelectorAll(kind==='scale'?'.proposal:checked':'.issue:checked')];
  if(!boxes.length)throw Error('请逐项选择需要确认的内容。');
  if(kind==='scale'&&boxes.length!==j.proposals.length)throw Error('请逐项选择本次全部比例建议后一次确认；不接受的比例请修改 Excel 后重新上传。');
  const rows=[...new Set(boxes.map(b=>b.dataset.row))];
  const reason=prompt(`${kind==='scale'?'应用比例建议':'跳过整行'}：${rows.join('、')}。\n请填写原因；取消则不提交。`);if(reason===null)return;if(!reason.trim())throw Error('请填写确认原因。');
  if(!confirm(`${kind==='scale'?'确认应用所选比例':'确认跳过指定行'}：\n${rows.join('\n')}\n原因：${reason}\n${kind==='skip'?'跳过后会重新检查全部剩余行，已有比例确认需要重新核对。':''}`))return;
  const selection={kind,row_ids:rows,issue_ids:kind==='skip'?boxes.map(b=>b.value):[],proposal_ids:kind==='scale'?boxes.map(b=>b.value):[],reason};
  await json('/confirm',{job_id:j.id,action:'decision',revision_hash:j.revision.revision_hash,selection});await load(j.id);
});}
async function download(id,filename){
  const j=current,turn=epoch;const response=await request(`/service/jobs/${j.id}/runs/${j.run.id}/artifacts/${id}`);
  const blob=await response.blob();if(turn!==epoch)return;
  const url=URL.createObjectURL(blob);
  if(filename.endsWith('.pdf')){
    closePreview();previewUrl=url;const renderingTurn=previewTurn;
    $('savePdf').href=url;$('savePdf').download=filename;$('previewCard').hidden=false;
    $('previewStatus').textContent='正在读取 PDF…';$('pageNumber').textContent='';
    $('previousPage').disabled=$('nextPage').disabled=true;
    $('previewCard').scrollIntoView({behavior:'smooth'});
    try{
      const pdf=await import('/satellite-heater/pdf.mjs');if(turn!==epoch||renderingTurn!==previewTurn)return;
      pdf.GlobalWorkerOptions.workerSrc='/satellite-heater/pdf.worker.mjs';
      previewTask=pdf.getDocument({data:new Uint8Array(await blob.arrayBuffer()),isEvalSupported:false,useSystemFonts:false});
      previewDocument=await previewTask.promise;if(turn!==epoch||renderingTurn!==previewTurn)return;
      await renderPdfPage(1);
    }catch(error){if(renderingTurn===previewTurn){$('previewStatus').textContent='预览未能显示，可点击“下载 PDF”查看。';throw error;}}
  }else{
    const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
}
$('upload').onsubmit=event=>{event.preventDefault();perform(async()=>{
  const file=$('file').files[0];if(!file||!file.name.toLowerCase().endsWith('.xlsx'))throw Error('请选择 xlsx 工作簿。');
  if(file.size>10*1024*1024)throw Error('Excel 文件上限为 10 MiB。');
  $('uploadButton').disabled=true;
  try{const response=await request('/service/jobs',{method:'POST',body:file,headers:{'content-type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','x-heater-name':encodeURIComponent($('name').value)}});const job=await response.json();await load(job.id);}
  finally{$('uploadButton').disabled=false;}
});};
$('closePreview').onclick=closePreview;$('refresh').onclick=()=>perform(list);
$('previousPage').onclick=()=>perform(()=>renderPdfPage(previewPage-1));
$('nextPage').onclick=()=>perform(()=>renderPdfPage(previewPage+1));
if(!session){$('connection').textContent='未选择会话';notice('请从 DSH 会话的“矩形加热器出图”工作区打开。');$('uploadButton').disabled=true;}
else perform(async()=>{await json('/context');await json('/service/capabilities');$('connection').textContent='后台已连接';await list();});
window.addEventListener('pagehide',()=>{epoch++;clearTimeout(poll);closePreview();});
