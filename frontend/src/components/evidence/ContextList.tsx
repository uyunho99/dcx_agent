'use client';
import { Badge, Button, Card } from '../ds';
import type { EvidenceContextStatus } from '@/lib/types';
import { rowBadge } from './evidenceView';
export function ContextList({rows,selected,disabled,onSelect,onRetry,onSkip,onRefresh,flags = {}}: {
  rows: EvidenceContextStatus[]; selected: string; disabled: boolean; flags?: Record<string,string[]>;
  onSelect: (id:string)=>void; onRetry:(id:string)=>void; onSkip:(id:string)=>void; onRefresh:(id:string)=>void;
}) {
  return <nav aria-label="Context 목록" className="min-w-0 space-y-3">{rows.map(row => <Card key={row.id} size="sm" className="min-w-0 space-y-2">
    <Button className="ds-wrap w-full" disabled={row.status !== 'done'} aria-current={selected === row.id ? 'true' : undefined} onClick={() => {if(row.status === 'done') onSelect(row.id);}}>
      {row.name || row.id} <Badge>{rowBadge(row.status)}</Badge>
    </Button>
    <p className="ds-t-caption">Coverage {row.coverage ?? 0}/6 · 새 발견 {row.counts.new ?? 0}</p>
    {flags[row.id]?.includes('undifferentiated_candidate') && <Badge tone="warning">⚠ 미분화 후보</Badge>}
    {row.status === 'done' && row.knownChanged && <div><p>Known Insight가 바뀌었습니다 · 새 발견 다시 계산</p><Button disabled={disabled} onClick={() => onRefresh(row.id)}>새 발견 다시 계산</Button></div>}
    {row.status === 'failed' && <div className="space-y-2"><p>이 Context의 근거를 찾지 못했습니다: {row.error ?? '검색 실패'}</p><div className="flex flex-wrap gap-2"><Button disabled={disabled} onClick={() => onRetry(row.id)}>다시 시도</Button><Button disabled={disabled} onClick={() => onSkip(row.id)}>건너뛰고 진행</Button></div></div>}
  </Card>)}</nav>;
}
