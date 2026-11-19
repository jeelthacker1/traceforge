'use client';
import {Background, Controls, ReactFlow} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type {GraphData} from '@/lib/api';
export default function ServiceGraph({data,onSelect}:{data:GraphData;onSelect:(id:string)=>void}) {
  const nodes=data.nodes.map((n,i)=>({id:n.id,position:{x:(i%3)*240,y:Math.floor(i/3)*150},data:{label:<div><strong>{n.id}</strong><br/><small>{n.events} events · {(n.error_rate*100).toFixed(1)}% errors</small><br/><small>{n.latency_ms?.toFixed(1)??'—'} ms</small></div>},style:{background:'#10202c',color:'#e7f0f6',border:`1px solid ${n.error_rate>0.1?'#f08a77':'#31515f'}`,borderRadius:12,width:195,padding:14}}));
  const edges=data.edges.map(e=>({id:e.source+'-'+e.target,source:e.source,target:e.target,label:`${e.count} calls`,style:{stroke:'#4ecbb3'},labelStyle:{fill:'#b6cbd5'},labelBgStyle:{fill:'#10202c'}}));
  return <div className="graph"><ReactFlow key={nodes.map(n=>n.id).join()} nodes={nodes} edges={edges} fitView colorMode="dark" onNodeClick={(_,n)=>onSelect(n.id)}><Background color="#29404d" gap={24}/><Controls/></ReactFlow>{!nodes.length&&<p className="graph-empty">No observed service relationships yet. Generate local traffic to begin.</p>}</div>
}
