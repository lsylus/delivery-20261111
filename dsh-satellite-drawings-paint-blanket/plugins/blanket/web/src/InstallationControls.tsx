import React from 'react';
export const defaultInstallation=()=>({x_direction:[1,0,0],rotation_deg:0,origin_mode:'bounds_min',offset_mm:[0,0]});
export function InstallationControls({setup,install,faces,busy,change,measure,preview,sectionError}:any){
 return <fieldset><legend>安装坐标 · 当前实例</legend>
 {setup.x_direction.map((v:number,i:number)=><label key={i}>安装X方向 {'XYZ'[i]}<input aria-label={`安装X方向 ${'XYZ'[i]}`} type="number" step="any" value={v} disabled={busy} onChange={e=>change({...setup,x_direction:setup.x_direction.map((q:number,j:number)=>i===j?(e.target.value===''?'':Number(e.target.value)):q)})}/></label>)}
 <p>方向使用模型世界坐标，投影到所选底面；Z轴指向设备内侧。也可选择同实例平面法向。</p>
 <button disabled={busy} onClick={()=>change({...setup,x_direction:setup.x_direction.map((v:number)=>-v)})}>反转安装X</button>
 <label>安装平面内旋转 度<input aria-label="安装平面内旋转 度" type="number" min="-180" max="180" value={setup.rotation_deg} disabled={busy} onChange={e=>change({...setup,rotation_deg:e.target.value===''?'':Number(e.target.value)})}/></label>
 <label>安装原点参照<select aria-label="安装原点参照" value={setup.origin_mode} disabled={busy} onChange={e=>change({...setup,origin_mode:e.target.value})}><option value="bounds_min">本实例投影范围最小角</option><option value="face_center">所选安装面中心</option></select></label>
 {setup.offset_mm.map((v:number,i:number)=><label key={i}>安装原点偏移 {'XY'[i]} mm<input aria-label={`安装原点偏移 ${'XY'[i]} mm`} type="number" step="any" value={v} disabled={busy} onChange={e=>change({...setup,offset_mm:setup.offset_mm.map((q:number,j:number)=>i===j?(e.target.value===''?'':Number(e.target.value)):q)})}/></label>)}
 <button disabled={busy||[...setup.x_direction,...setup.offset_mm,setup.rotation_deg].some((v:any)=>typeof v!=='number'||!Number.isFinite(v))} onClick={measure}>核对安装坐标与分段范围</button>
 {preview?<><p data-testid="installation-range">分段X有效开区间：({preview.section_x_open_interval_mm.map((v:number)=>v.toFixed(6)).join(', ')}) mm，最多7处，递增且不重复。</p><p data-testid="installation-origin">世界原点 mm：{preview.frame.origin.map((v:number)=>v.toFixed(6)).join(', ')}</p><p data-testid="installation-axes">X：{preview.frame.x_axis.map((v:number)=>v.toFixed(6)).join(', ')}；Z：{preview.frame.z_axis.map((v:number)=>v.toFixed(6)).join(', ')}</p></>:<p data-testid="installation-unmeasured">请核对当前坐标。分段数值均相对该原点沿安装X轴，以毫米计。</p>}
 {sectionError&&<p role="alert">分段须为有效范围内至多7个递增且不重复的数值</p>}
 <p>重选底面、改轴或改原点会清空分段；重新生成罩形后旧净片、固定点和图纸失效。安装方案仍待工程复核。</p>
 </fieldset>;
}
