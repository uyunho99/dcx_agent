'use client';
import { Badge, Banner, Button, Card, Input } from '../ds';
import type { SegmentContext } from '@/lib/types';
import type { EditorProps } from './ClusterLayer';
import { QualityBadges } from './QualityBadges';
import { bulkConfirmWarning, granularityBadge } from './segmentView';
export function ContextLayer({ contexts, emptyRatio, disabled, edits, onEdit, onConfirm, onBulk }: EditorProps & {
    contexts: SegmentContext[];
    emptyRatio: number;
    onBulk: () => void;
}) {
    const values = (c: SegmentContext) => ({ name: edits[c.id]?.name ?? c.name ?? c.nameDraft ?? '', action: edits[c.id]?.action ?? c.action ?? c.actionDraft ?? '' });
    const invalid = (c: SegmentContext) => { const v = values(c); return !v.name.trim() || !v.action.trim(); };
    const warning = bulkConfirmWarning(contexts);
    const granularity = granularityBadge(contexts.flatMap(c => c.flags), contexts.length);
    return <section className="min-w-0 space-y-4" aria-label="Context 이름과 행동">{granularity && <Badge tone="warning">{granularity}</Badge>}<p className="ds-t-caption">Core 중 목적 · 제약 빈 비율 {Math.round(emptyRatio * 100)}% · 표본 추출(6.5) Context당 100건</p>{contexts.length === 0 && <Card>Context가 없습니다.</Card>}{contexts.map(c => <Card key={c.id} className="space-y-3"><p>{c.id} · 문서 {c.docs}건</p>{c.confirmed && !edits[c.id] && <Badge tone="success">확정됨</Badge>}{c.flags.includes('counter_context') && <Banner tone="warning"><Badge tone="danger">반례</Badge> Persona 평균보다 감성이 낮고 문서가 적습니다. 다른 Context의 기대를 반박하는 담론으로 남깁니다.</Banner>}{c.flags.includes('few_docs') && <Banner tone="warning">문서가 적어 Context를 나누지 않았습니다({c.docs}건).</Banner>}{(!c.nameDraft || !c.actionDraft) && !c.confirmed && <Banner tone="warning">초안을 만들지 못했습니다. 직접 입력하세요.</Banner>}<div className="grid grid-cols-2 gap-3"><Input label={`${c.id} Context 이름`} value={values(c).name} disabled={disabled} onChange={e => onEdit(c.id, { name: e.target.value })}/><Input label={`${c.id} 행동 요약`} value={values(c).action} disabled={disabled} onChange={e => onEdit(c.id, { action: e.target.value })}/></div><p className="break-words">LDA 상위 어휘 · {c.keywords.join(' · ')} · 주된 제약: {c.dominantConstraint ?? '없음'}</p><QualityBadges quality={c.quality} layer="L3"/><Button disabled={disabled || invalid(c)} onClick={() => onConfirm(c.id)}>Context 확정</Button></Card>)}<div className="flex flex-wrap items-center gap-3"><Button variant="primary" disabled={disabled || !contexts.length || contexts.some(invalid)} onClick={onBulk}>이 Persona의 Context 모두 확정</Button>{warning && <Badge tone="danger">{warning}</Badge>}{contexts.some(c => c.flags.includes('few_docs')) && <Badge tone="warning">문서 부족 Context 포함</Badge>}</div></section>;
}
