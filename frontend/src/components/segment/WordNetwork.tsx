'use client';
import { useMemo } from 'react';
import SNAGraph from '../SNAGraph';
import type { SegmentPersona, SNANode } from '@/lib/types';
// SNAGraph mutates its inputs and uses HTML tooltips; give it copies and escaped labels.
const escape = (text: string) => text.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
export function WordNetwork({ network }: {
    network: SegmentPersona['network'];
}) {
    const graph = useMemo(() => { const nodes: SNANode[] = network.nodes.slice(0, 60).map(n => ({ id: n.id, name: escape(n.id), type: (['cluster', 'persona', 'product'] as const)[Math.abs(n.persona) % 3], size: 6 + Math.max(0, Math.min(1, n.score)) * 12 })); const ids = new Set(nodes.map(n => n.id)); return { nodes, links: network.edges.filter(e => ids.has(e.source) && ids.has(e.target)).map(e => ({ ...e, value: e.weight })) }; }, [network]);
    return <figure className="min-w-0 overflow-hidden"><figcaption className="ds-t-label">어휘 네트워크 · 상위 60개</figcaption><SNAGraph {...graph}/><details><summary>공동체별 어휘 보기</summary>{Array.from(new Set(network.nodes.map(n => n.persona))).map(p => <p key={p}>공동체 {p + 1}: {network.nodes.filter(n => n.persona === p).map(n => n.id).join(' · ')}</p>)}</details></figure>;
}
