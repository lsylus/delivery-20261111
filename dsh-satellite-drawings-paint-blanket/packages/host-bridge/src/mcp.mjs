import readline from 'node:readline';
import {toolCatalog,callTool} from './commands.mjs';
export function serveMcp(module,context) {
  const input=readline.createInterface({input:process.stdin});
  input.on('line',async line=>{
    let req;try{req=JSON.parse(line);}catch{return;}
    if(req.id===undefined)return;
    try{
      let result;
      if(req.method==='initialize')result={protocolVersion:'2024-11-05',capabilities:{tools:{}},serverInfo:{name:`satellite-${module}`,version:'0.1.0'}};
      else if(req.method==='tools/list')result={tools:toolCatalog(module)};
      else if(req.method==='tools/call')result={content:[{type:'text',text:JSON.stringify(await callTool(module,req.params,context))}]};
      else throw Error('unsupported_method');
      process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:req.id,result})+'\n');
    }catch(e){process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:req.id,error:{code:-32000,message:e.message}})+'\n');}
  });
}
