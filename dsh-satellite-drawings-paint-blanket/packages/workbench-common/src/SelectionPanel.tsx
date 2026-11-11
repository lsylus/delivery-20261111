import React from 'react';
export function SelectionPanel({selected}:{selected:any[]}){return <section><h3>当前选择 · {selected.length} 个面</h3><ul data-testid="selected-faces">{selected.map((r,i)=><li key={i}>{r.instance_id} / {r.entity_id}</li>)}</ul></section>;}
