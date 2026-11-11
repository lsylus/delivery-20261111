import React from 'react';
export function ChecksPanel({dirty,revision}:{dirty:boolean;revision:string}){return <section><h3>检查与版本</h3><p data-testid="dirty">{dirty?'未保存草稿；旧检查已过期':'已保存工程状态'}</p><p data-testid="revision">{revision}</p><p>当前没有业务计算结果。二维图仅供选择映射测试。</p><p>DWG 未开放；最终须通过 AutoCAD 打开、编辑、保存、重开验收。</p></section>;}
