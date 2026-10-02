'use client';
import { useState } from 'react';
import type { PersonaContextRow, PersonaSortDirection } from '../../lib/types';
import { sortContexts, zoneName, formatMetric, formatCount } from './personaView';
import { ProvisionalBadge } from './ProvisionalBadge';
const columns = [['context_id','ID'], ['name','이름'], ['persona_name','Persona'], ['i','중요도'], ['s','만족도'], ['odi','기회'], ['zone','구역'], ['star','★']] as const;
type Key = typeof columns[number][0];
export type ContextTableProps = { rows: PersonaContextRow[]; highlightedId?: string | null; onHighlight?: (id: string | null) => void; onOpenCard: (personaId: string, contextId: string) => void };
export function ContextTable({ rows, highlightedId, onHighlight, onOpenCard }: ContextTableProps) {
  const [sort, setSort] = useState<{key: Key; direction: PersonaSortDirection}>({key:'odi',direction:'desc'});
  const sorted = sortContexts(rows.map(row => ({...row, persona_name: row.persona_name || row.persona_id})), sort.key, sort.direction);
  return <table className="ds-tbl"><caption>Context {formatCount(rows.length)}개 · 행을 고르면 맵의 점이 강조됩니다 · 기회 <ProvisionalBadge/></caption><thead><tr>{columns.map(([key,label]) => <th scope="col" key={key} aria-sort={sort.key === key ? sort.direction === 'asc' ? 'ascending' : 'descending' : 'none'}><button type="button" className="ds-btn ds-quiet ds-sm" style={{ padding: 0 }} onClick={() => setSort({key,direction:sort.key === key && sort.direction === 'desc' ? 'asc' : 'desc'})}>{label}</button></th>)}<th scope="col">카드</th></tr></thead><tbody>{sorted.map(row => <tr key={row.context_id} tabIndex={0} data-highlighted={highlightedId === row.context_id} className={highlightedId === row.context_id ? 'ds-sel' : undefined} onFocus={() => onHighlight?.(row.context_id)} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) onHighlight?.(null); }} onMouseEnter={() => onHighlight?.(row.context_id)} onMouseLeave={event => { if (!event.currentTarget.contains(event.currentTarget.ownerDocument.activeElement)) onHighlight?.(null); }}>
    <th scope="row">{row.context_id}{row.counter && ' · 반례'}</th><td>{row.name || '—'}</td><td>{row.persona_name}</td><td>{formatMetric(row.i)}</td><td>{formatMetric(row.s)}</td><td>{formatMetric(row.odi)}</td><td>{zoneName(row.zone)}</td><td>{row.star ? <span title="몰랐고 기회도 큰 지점">★</span> : '—'}</td><td><button type="button" className="ds-btn ds-quiet ds-sm" style={{ whiteSpace: 'normal', height: 'auto', minHeight: 36 }} onClick={() => onOpenCard(row.persona_id,row.context_id)}>카드 열기</button></td>
  </tr>)}</tbody></table>;
}
