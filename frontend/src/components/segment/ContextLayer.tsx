'use client';
import { useEffect, useRef, useState } from 'react';
import { getEvidenceContext } from '@/lib/api/evidence';
import { displayError } from '@/lib/api/errors';
import { Badge, Banner, Button, Card, TextArea } from '../ds';
import type { SegmentContext } from '@/lib/types';
import type { EditorProps } from './ClusterLayer';
import { SourceBrowser } from './SourceBrowser';
import { QualityBadges } from './QualityBadges';
import { bulkConfirmWarning, granularityBadge } from './segmentView';
export function ContextLayer({ sid, version, contexts, emptyRatio, disabled, edits, onEdit, onConfirm, onBulk }: EditorProps & {
    sid?: string;
    version?: string;
    contexts: SegmentContext[];
    emptyRatio: number;
    onBulk: () => void;
}) {
    const values = (c: SegmentContext) => ({ name: edits[c.id]?.name ?? c.name ?? c.nameDraft ?? '', action: edits[c.id]?.action ?? c.action ?? c.actionDraft ?? '' });
    const invalid = (c: SegmentContext) => { const v = values(c); return !v.name.trim() || !v.action.trim(); };
    const warning = bulkConfirmWarning(contexts);
    const granularity = granularityBadge(contexts.flatMap(c => c.flags), contexts.length);
    return <section className="min-w-0 space-y-4" aria-label="Context 이름과 행동">{granularity && <Badge tone="warning">{granularity}</Badge>}<p className="ds-t-caption">Core 중 목적 · 제약 빈 비율 {Math.round(emptyRatio * 100)}% · 표본 추출(6.5) Context당 25건</p>{contexts.length === 0 && <Card>Context가 없습니다.</Card>}{contexts.map(c => <Card key={c.id} className="space-y-3"><p>{c.id} · 문서 {c.docs}건</p>{c.confirmed && !edits[c.id] && <Badge tone="success">확정됨</Badge>}{c.flags.includes('undifferentiated_candidate') && <CandidateSources key={`${sid}:${version}:${c.id}`} sid={sid} version={version} contextId={c.id}/>}
{c.flags.includes('counter_context') && <Banner tone="warning"><Badge tone="danger">반례</Badge> Persona 평균보다 감성이 낮고 문서가 적습니다. 다른 Context의 기대를 반박하는 담론으로 남깁니다.</Banner>}{c.flags.includes('few_docs') && <Banner tone="warning">문서가 적어 Context를 나누지 않았습니다({c.docs}건).</Banner>}{(!c.nameDraft || !c.actionDraft) && !c.confirmed && <Banner tone="warning">초안을 만들지 못했습니다. 직접 입력하세요.</Banner>}<div className="grid gap-3 lg:grid-cols-2"><TextArea label={`${c.id} Context 이름`} value={values(c).name} disabled={disabled} onChange={e => onEdit(c.id, { name: e.target.value })}/><TextArea label={`${c.id} 행동 요약`} value={values(c).action} disabled={disabled} onChange={e => onEdit(c.id, { action: e.target.value })}/></div><p className="break-words">LDA 상위 어휘 · {c.keywords.join(' · ')} · 주된 제약: {c.dominantConstraint ?? '없음'}</p><QualityBadges quality={c.quality} layer="L3"/><SourceBrowser sid={sid} version={version} filter={{ context: c.id }} total={c.docs}/><Button disabled={disabled || invalid(c)} onClick={() => onConfirm(c.id)}>Context 확정</Button></Card>)}<div className="flex flex-wrap items-center gap-3"><Button variant="primary" disabled={disabled || !contexts.length || contexts.some(invalid)} onClick={onBulk}>이 Persona의 Context 모두 확정</Button>{warning && <Badge tone="danger">{warning}</Badge>}{contexts.some(c => c.flags.includes('few_docs')) && <Badge tone="warning">문서 부족 Context 포함</Badge>}</div></section>;
}

function CandidateSources({ sid, version, contextId }: { sid?: string; version?: string; contextId: string }) {
    const [sources, setSources] = useState<{ id: string; text: string }[] | null>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const pending = useRef(false);
    const active = useRef(true);
    useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
    async function load() {
        if (pending.current || sources) return;
        if (!sid) { setError('세션을 먼저 선택하세요.'); return; }
        pending.current = true;
        setLoading(true);
        setError('');
        try {
            const result = await getEvidenceContext(sid, contextId, 'all', version);
            const documents = new Map([...result.items, ...result.counter, ...result.rare].map(item => [item.docId, item.text]));
            if (active.current) setSources(result.undifferentiated.slice(0, 3).map(id => ({ id, text: documents.get(id) ?? id })));
        } catch (e) {
            if (active.current) setError(displayError(e));
        } finally {
            pending.current = false;
            if (active.current) setLoading(false);
        }
    }
    return <details onToggle={event => { if (event.currentTarget.open) return load(); }}>
        <summary className="cursor-pointer"><Badge tone="warning">새 Context 후보 — 원문 3건</Badge></summary>
        {loading && <p role="status">원문을 불러오는 중…</p>}
        {error && <Banner tone="danger" actions={<Button onClick={() => void load()}>다시 불러오기</Button>}>{error}</Banner>}
        {sources && <ul className="space-y-3">{sources.map((source, index) => <li key={`${source.id}:${index}`} className="whitespace-pre-wrap break-words">{source.text}</li>)}</ul>}
        {sources?.length === 0 && <p>후보 원문이 없습니다.</p>}
    </details>;
}
