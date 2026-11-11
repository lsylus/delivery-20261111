export const PROTECTION_RENDER_ORDER=30;

export function selectionOverlayPresentation(installation=false){
 return installation?{
  material:{color:'#06b6d4',depthTest:true,depthWrite:true,transparent:false,opacity:1},
  renderOrder:10,
 }:{
  material:{color:'#16a34a',depthTest:false,depthWrite:false,transparent:true,opacity:.72},
  renderOrder:20,
 };
}
