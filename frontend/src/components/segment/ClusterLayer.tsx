'use client';
import { SourceBrowser } from './SourceBrowser';
import { Badge, Button, Input, TextArea } from '../ds';
import type { SegmentCluster, SegmentRepresentative } from '@/lib/types';
import { QualityBadges } from './QualityBadges';
import { ChannelBar } from './ChannelBar';
export type Edit = {
    name?: string;
    desire?: string;
    goals?: string[];
    action?: string;
};
export type EditorProps = {
    disabled: boolean;
    edits: Record<string, Edit>;
    onEdit: (id: string, edit: Edit) => void;
    onConfirm: (id: string) => void;
};
export function Representatives({ reps }: {
    reps: SegmentRepresentative[];
}) {
    return <details><summary className="cursor-pointer ds-t-caption">대표 원문 {reps.length}건</summary>{reps.map((rep, i) => <blockquote key={`${rep.docId}:${i}`} className="my-3 border-l-2 pl-3 break-words"><p>{rep.text}</p><cite className="ds-t-caption">{rep.source} · {rep.field}{rep.idx !== null ? ` ${rep.idx}` : ''}</cite></blockquote>)}</details>;
}
export function ClusterLayer({ sid, version, clusters, disabled, edits, onEdit, onConfirm, onRequest }: EditorProps & {
    sid?: string;
    version?: string;
    clusters: SegmentCluster[];
    onRequest: (id: string, kind: 'split' | 'merge', note: string) => void;
}) {
    const primary = clusters.find(c => !c.confirmed || edits[c.id])?.id;
    return <section aria-label="Cluster 이름" className="divide-y rounded-xl border border-[var(--line)] px-5">{clusters.map(c => {
            const name = edits[c.id]?.name ?? c.name ?? c.nameDraft ?? '';
            return <article key={c.id} className="grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-5 py-5"><div className="min-w-0 space-y-3"><p className="ds-t-caption">{c.id} · 문서 {c.docs.toLocaleString('ko-KR')}건</p><TextArea minRows={1} label={`${c.id} 이름`} value={name} disabled={disabled} onChange={e => onEdit(c.id, { name: e.target.value })}/>{c.confirmed && !edits[c.id] && <Badge tone="success">확정됨</Badge>}<QualityBadges quality={c.quality}/>{c.quality.flags?.includes('few_docs') && <Badge tone="warning">문서가 적어({c.docs}건) 군집이 불안정할 수 있습니다.</Badge>}{!c.nameDraft && !c.name && <p>초안을 만들지 못했습니다. 직접 입력하세요.</p>}<Representatives reps={c.reps}/><SourceBrowser sid={sid} version={version} filter={{ cluster: c.id }} total={c.docs}/><Button variant={primary === c.id ? 'primary' : 'secondary'} disabled={disabled || !name.trim()} onClick={() => onConfirm(c.id)}>이름 확정</Button><details><summary className="cursor-pointer ds-t-caption">분리 · 병합 요청 남기기</summary><form className="space-y-2" onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); onRequest(c.id, data.get('kind') as 'split' | 'merge', String(data.get('note') ?? '')); }}><label>요청 종류<select name="kind" className="ds-inp" disabled={disabled}><option value="split">분리</option><option value="merge">병합</option></select></label><Input name="note" label="요청 메모" required disabled={disabled}/><button className="ds-btn ds-secondary" disabled={disabled}>요청 저장</button></form>{c.requests.map((r, i) => <p key={i}>{r.kind === 'split' ? '분리' : '병합'} · {r.note}</p>)}</details></div><div className="min-w-0 space-y-3 break-words"><h3 className="ds-t-label">키워드</h3><p>{c.keywords.map(k => `#${k}`).join(' ')}</p><h3 className="ds-t-label">채널</h3><ChannelBar channels={c.channels}/></div></article>;
        })}</section>;
}
