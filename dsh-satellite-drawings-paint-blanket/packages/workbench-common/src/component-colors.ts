type InstanceNode={instance_id:string;parent_instance_id:string|null};

const GOLDEN_ANGLE=137.507764;

function componentColor(index:number){
 const hue=(212+index*GOLDEN_ANGLE)%360;
 const saturation=[62,72,54][Math.floor(index/12)%3];
 const lightness=[48,57,43,64][Math.floor(index/3)%4];
 return `hsl(${hue.toFixed(1)}, ${saturation}%, ${lightness}%)`;
}

/** Group rendered leaves by the top-level Component below the first branching assembly. */
export function componentColors(instances:InstanceNode[],physicalInstanceIds:Iterable<string>){
 const nodes=new Map(instances.map(node=>[node.instance_id,node]));
 const childCounts=new Map<string,number>();
 for(const node of instances)if(node.parent_instance_id)childCounts.set(node.parent_instance_id,(childCounts.get(node.parent_instance_id)||0)+1);
 const physical=new Set(physicalInstanceIds),groupByInstance=new Map<string,string>();
 for(const id of physical){
  const path:InstanceNode[]=[],seen=new Set<string>();let node=nodes.get(id);
  while(node){
   if(seen.has(node.instance_id))throw Error('装配层级存在循环，无法分配组件颜色');
   seen.add(node.instance_id);path.push(node);node=node.parent_instance_id?nodes.get(node.parent_instance_id):undefined;
  }
  path.reverse();let group=id;
  for(let i=1;i<path.length;i++)if((childCounts.get(path[i-1].instance_id)||0)>1){group=path[i].instance_id;break;}
  groupByInstance.set(id,group);
 }
 const groups:string[]=[];
 for(const node of instances){const group=groupByInstance.get(node.instance_id);if(group&&!groups.includes(group))groups.push(group);}
 for(const group of groupByInstance.values())if(!groups.includes(group))groups.push(group);
 const colorByGroup=new Map(groups.map((group,index)=>[group,componentColor(index)]));
 return new Map([...groupByInstance].map(([id,group])=>[id,colorByGroup.get(group)!]));
}
