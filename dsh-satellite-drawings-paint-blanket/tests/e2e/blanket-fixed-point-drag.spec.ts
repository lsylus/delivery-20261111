import {test,expect} from '@playwright/test';
import {build} from 'esbuild';
import {createServer,Server} from 'node:http';
import path from 'node:path';
let server:Server,origin:string;
test.beforeAll(async()=>{
 const component=path.resolve('plugins/blanket/web/src/BlanketDrawing.tsx');
 const bundle=await build({bundle:true,write:false,format:'iife',jsx:'automatic',stdin:{loader:'tsx',resolveDir:process.cwd(),contents:`
 import React,{useState} from 'react';import {createRoot} from 'react-dom/client';import {BlanketDrawing} from ${JSON.stringify(component)};
 const net={revision_id:'initial',drawing_document:{revision_id:'initial',entities:[{id:'bounds',kind:'polyline',layer:'CUT',points:[[0,-40],[240,-40],[240,200],[0,200]]}]},panels:[{key:'part',piece_id:'piece',transform:{rotation:[[0,-1],[-1,0]],translation:[100,120]}}],pieces:[{id:'piece',layout:{rotation_rad:.31,translation_mm:[80,-20]}}],edges:{},seams:[],fixed_points:[{id:'anchor',panel_key:'part',uv_mm:[20,30]}]};
 function App(){const [value,setValue]=useState(net),[target,setTarget]=useState(null),[error,setError]=useState('');return <><div id="calls" data-calls="0"/><p role="alert">{error}</p><div style={{width:1000,margin:'24px 50px'}}><BlanketDrawing net={value} target={target} onTarget={(kind,id)=>setTarget({kind,id})} onPointMove={async(id,panelKey,uv)=>{window.moves.push({id,panelKey,uv});document.querySelector('#calls').setAttribute('data-calls',String(window.moves.length));await new Promise(r=>setTimeout(r,50));if(uv.some(v=>v<0||v>80)){setError('定位标记不能落在孔洞或裁片材料之外；已保留原位置。');return false;}setValue({...value,revision_id:'saved',drawing_document:{...value.drawing_document,revision_id:'saved'},fixed_points:[{id,panel_key:panelKey,uv_mm:uv}]});return true;}}/></div></>;}window.moves=[];createRoot(document.getElementById('root')).render(<App/>);
 `}});
 const html='<div id="root"></div><script>'+bundle.outputFiles[0].text+'</script>';
 server=createServer((_req,res)=>{res.setHeader('Content-Type','text/html');res.end(html);});await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));origin='http://127.0.0.1:'+(server.address() as any).port;
});
test.afterAll(async()=>{await new Promise<void>(r=>server.close(()=>r()));});
// The expected screen position is independently derived from this fixture's reflected panel and rotated piece.
async function clientForUV(page:any,uv:number[]){return page.getByTestId('blanket-drawing').evaluate((svg:SVGSVGElement,uv:number[])=>{const a=100-uv[1],b=120-uv[0],c=Math.cos(.31),s=Math.sin(.31),q=new DOMPoint(a*c-b*s+80,a*s+b*c-20).matrixTransform(svg.getScreenCTM()!);return [q.x,q.y];},uv);}
async function dragTo(page:any,uv:number[]){const marker=page.getByTestId('point-anchor');await marker.scrollIntoViewIfNeeded();const box=await marker.boundingBox(),to=await clientForUV(page,uv);await page.mouse.move(box!.x+box!.width/2,box!.y+box!.height/2);await page.mouse.down();await page.mouse.move(to[0],to[1],{steps:8});await page.mouse.up();await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-point-saving','false');}
test('drag uses SVG inverse, reflected panel and rotated piece after zoom/pan',async({page})=>{
 await page.goto(origin);await page.getByLabel('二维缩放').fill('2');await page.getByRole('button',{name:'右',exact:true}).click();await page.getByRole('button',{name:'下',exact:true}).click();await dragTo(page,[28,36]);
 await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-revision','saved');const moves=await page.evaluate(()=>(window as any).moves);expect(moves).toHaveLength(1);expect(moves[0].id).toBe('anchor');expect(moves[0].panelKey).toBe('part');expect(moves[0].uv[0]).toBeCloseTo(28,4);expect(moves[0].uv[1]).toBeCloseTo(36,4);
});
test('rejected drop restores original marker and reports failure',async({page})=>{
 await page.goto(origin);const marker=page.getByTestId('point-anchor'),before=await marker.getAttribute('cx');await dragTo(page,[-10,35]);await expect(page.getByRole('alert')).toContainText('已保留原位置');await expect(marker).toHaveAttribute('cx',before!);await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-revision','initial');
});
test('click and cancelled drag do not submit a move',async({page})=>{
 await page.goto(origin);const marker=page.getByTestId('point-anchor');await marker.click();await expect(page.locator('#calls')).toHaveAttribute('data-calls','0');const box=await marker.boundingBox();await page.mouse.move(box!.x+box!.width/2,box!.y+box!.height/2);await page.mouse.down();await page.mouse.move(box!.x+30,box!.y+20);await marker.dispatchEvent('pointercancel',{pointerId:1});await page.mouse.up();await expect(page.locator('#calls')).toHaveAttribute('data-calls','0');
});

test('focus control centers a marker and supports a real drag without repeated panning',async({page})=>{
 await page.goto(origin);await page.getByRole('button',{name:'聚焦定位标记',exact:true}).click();const marker=page.getByTestId('point-anchor'),mb=await marker.boundingBox(),sb=await page.getByTestId('blanket-drawing').boundingBox();expect(Math.abs(mb!.x+mb!.width/2-sb!.x-sb!.width/2)).toBeLessThan(.01);expect(Math.abs(mb!.y+mb!.height/2-sb!.y-sb!.height/2)).toBeLessThan(.01);expect(Number(await page.getByLabel('二维缩放').inputValue())).toBeGreaterThan(1);await dragTo(page,[28,36]);await expect(page.getByTestId('blanket-drawing')).toHaveAttribute('data-revision','saved');
});
