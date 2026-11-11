export type ModelRef={project_id:string;model_id:string;model_revision:number;assembly_digest:string};
export type FaceRef=ModelRef&{instance_id:string;entity_kind:'face';entity_id:string;signature:any};
export type Identity={owner_id:string;session_id:string;module:'paint'|'blanket';host_mode:string};
export type Loaded={identity:Identity;project:any;revision:any;snapshot:any;map:any;glb:ArrayBuffer;hash:string;checks:any[];paintResult?:any;paintRecommendations?:any;paintBatchResult?:any;blanketResult?:any;blanketNet?:any};
