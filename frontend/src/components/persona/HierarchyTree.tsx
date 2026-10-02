export type HierarchyNode = { id: string; name: string; doc_count: number; children?: HierarchyNode[] };
export function HierarchyTree({ root }: { root: HierarchyNode }) {
  const positioned: { node: HierarchyNode; depth: number; parent?: number }[] = [];
  function visit(node: HierarchyNode, depth: number, parent?: number) {
    const index = positioned.length; positioned.push({node,depth,parent});
    node.children?.forEach(child => visit(child,depth + 1,index));
  }
  visit(root,0);
  const max = Math.max(1,...positioned.map(({node}) => node.doc_count));
  const width = Math.max(600, Math.max(...positioned.map(p => p.depth)) * 170 + 200);
  return <figure style={{margin:0}}><figcaption className="ds-t-label">제품 → Cluster → Persona → Context · 노드 크기 = 문서 수</figcaption><svg viewBox={`0 0 ${width} ${positioned.length * 64 + 24}`} role="img" aria-label={positioned.map(({node}) => `${node.name} 문서 ${node.doc_count}건`).join(', ')} style={{width:'100%'}}>
    {positioned.map(({node,depth,parent},index) => <g key={node.id}>{parent !== undefined && <line x1={32 + positioned[parent].depth * 170} y1={32 + parent * 64} x2={32 + depth * 170} y2={32 + index * 64} stroke="var(--line-strong)"/>}<circle cx={32 + depth * 170} cy={32 + index * 64} r={24 * Math.sqrt(Math.max(0,node.doc_count) / max)} fill="var(--ink)"/><text x={62 + depth * 170} y={36 + index * 64} fontSize={12} fill="var(--ink-strong)">{node.name} · {node.doc_count}건</text></g>)}
  </svg></figure>;
}
