'use client';
import { useEffect, useState, type KeyboardEvent } from 'react';
import { Badge, Popover } from '@/components/ds';
import { useSidebarAuto } from '@/components/sidebarAuto';
import type { Destination, Keyword, Rejection } from '@/lib/api/keywords';
import { isMoveShortcut } from '@/lib/logic/keywordKeys';
import { badgeLabels } from './taxonomy';
import { RejectPopover } from './RejectPopover';
import { keywordLabel, keywordTitle } from './keywordDisplay';
export function KeywordChip({ keyword: k, groups, tabIndex, onFocus, onKeyDown, onReview, onMove, disabled }: {
  keyword: Keyword; groups: Destination[]; tabIndex: number; onFocus: () => void; onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  onReview: (k: Keyword, rejection: Rejection | null, destination?: Destination) => Promise<void>; onMove: (k: Keyword, to: Destination) => Promise<void>; disabled: boolean;
}) {
  const [mode, setMode] = useState<'reject' | 'move' | null>(null);
  const { request } = useSidebarAuto();
  useEffect(() => { if (mode !== null) return request(); }, [mode, request]);
  const labels = [...new Set([...(k.badges ?? []).map(b => badgeLabels[b]).filter(Boolean), ...(k.origin === 'manual' ? ['수동'] : k.origin === 'suggested' ? ['추천'] : []), ...(k.volume?.source === 'unconnected' ? ['미연결'] : []), ...(k.volume?.error ? ['조회 실패'] : [])])];
  const volume = k.volume?.monthly;
  const label = keywordLabel(k);
  const toggle = () => { if (k.status === 'rejected') void onReview(k, null).catch(() => {}); else setMode('reject'); };
  return <Popover label={`${label} ${mode === 'move' ? '이동' : '거절 사유'}`} open={mode !== null} onOpenChange={open => setMode(open ? 'reject' : null)} renderTrigger={({ ref, props }) => <button {...props} ref={ref} role="option" aria-selected={k.status === 'rejected'} title={keywordTitle(k)} aria-label={[label, volume != null ? `월간 검색량 ${volume}` : '', ...labels, k.status === 'rejected' ? '거절됨' : ''].filter(Boolean).join(', ')} data-keyword-id={k.id} tabIndex={tabIndex} disabled={disabled} onFocus={onFocus} onClick={toggle} className={`kw-chip ${k.status === 'rejected' ? 'kw-rejected' : ''}`} draggable={!disabled} onDragStart={event => { event.dataTransfer.setData('text/plain', k.id); event.dataTransfer.effectAllowed = 'move'; }} onKeyDown={event => {
    if (isMoveShortcut(event.nativeEvent)) { event.preventDefault(); setMode('move'); }
    else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); }
    else onKeyDown(event);
  }}>{label}{volume != null && <span className="ds-t-caption">{volume.toLocaleString('ko-KR')}</span>}{labels.map(label => <Badge key={label}>{label}</Badge>)}{k.status === 'rejected' && <Badge>거절됨</Badge>}</button>}>
    {mode && <RejectPopover key={mode} initial={k.reject} groups={groups} moving={mode === 'move'} onCancel={() => setMode(null)} onConfirm={async (reject, to) => { if (mode === 'move' && to) await onMove(k, to); else await onReview(k, reject, to); setMode(null); }} />}
  </Popover>;
}
