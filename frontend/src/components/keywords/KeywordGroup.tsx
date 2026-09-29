'use client';
import { useRef, useState } from 'react';
import { Badge, Banner, Button, Input } from '@/components/ds';
import type { Destination, Keyword, Rejection } from '@/lib/api/keywords';
import { nextFocus } from '@/lib/logic/nextFocus';
import { groupLabel } from './taxonomy';
import { KeywordChip } from './KeywordChip';
export function KeywordGroup({ group, keywords, groups, collapsed, toggle, disabled, onAdd, onSuggest, onMove, onReview }: {
  group: Destination; keywords: Keyword[]; groups: Destination[]; collapsed: boolean; toggle: () => void; disabled: boolean;
  onAdd: (word: string, group: Destination, origin: 'manual' | 'suggested') => Promise<boolean>;
  onSuggest: (group: Destination) => Promise<string[]>; onMove: (k: Keyword | string, to: Destination) => Promise<void>;
  onReview: (k: Keyword, reject: Rejection | null, to?: Destination) => Promise<void>;
}) {
  const list = useRef<HTMLDivElement>(null); const [focused, setFocused] = useState(''); const [adding, setAdding] = useState(false);
  const [word, setWord] = useState(''); const [suggestions, setSuggestions] = useState<string[] | null>(null); const [busy, setBusy] = useState(false); const [over, setOver] = useState(false);
  const active = keywords.some(k => k.id === focused) ? focused : keywords[0]?.id;
  async function add(value: string, origin: 'manual' | 'suggested') { setBusy(true); try { if (await onAdd(value, group, origin)) { if (origin === 'manual') setWord(''); else setSuggestions(s => s?.filter(w => w !== value) ?? null); } } finally { setBusy(false); } }
  return <section className={`kw-group ${over ? 'kw-drop' : ''}`} onDragOver={event => { if (!disabled) { event.preventDefault(); setOver(true); event.dataTransfer.dropEffect = 'move'; } }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setOver(false); }} onDrop={event => { event.preventDefault(); setOver(false); const id = event.dataTransfer.getData('text/plain'); if (id && !disabled) void onMove(id, group).catch(() => {}); }}>
    <div className="kw-group-head"><Button size="sm" variant="quiet" aria-expanded={!collapsed} onClick={toggle}>{groupLabel(group)} {collapsed ? '펼치기' : '접기'}</Button><Badge>{keywords.length}</Badge><Button size="sm" variant="quiet" disabled={disabled} onClick={() => { setAdding(!adding); if (collapsed) toggle(); }}>직접 추가하기</Button>{over && <span className="ds-t-caption">여기에 놓으면 이동합니다</span>}</div>
    {!collapsed && <div className="kw-group-body"><div ref={list} role="listbox" aria-label={groupLabel(group)} aria-multiselectable="true" className="kw-chip-list">{keywords.map(k => <KeywordChip key={k.id} keyword={k} groups={groups} disabled={disabled} tabIndex={active === k.id ? 0 : -1} onFocus={() => setFocused(k.id)} onReview={onReview} onMove={onMove} onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); const buttons = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('[data-keyword-id]') ?? []);
      const rows: string[][] = []; let lastTop = -Infinity;
      for (const button of buttons) { const top = button.getBoundingClientRect().top; if (Math.abs(top - lastTop) > 4) { rows.push([]); lastTop = top; } rows[rows.length - 1].push(button.dataset.keywordId!); }
      const next = nextFocus(rows, k.id, event.key); buttons.find(b => b.dataset.keywordId === next)?.focus();
    }} />)}</div>
    {adding && <fieldset disabled={disabled || busy} className="space-y-3 mt-4"><form className="kw-add" onSubmit={e => { e.preventDefault(); if (word.trim()) void add(word.trim(), 'manual'); }}><Input label={`${groupLabel(group)} 키워드`} value={word} onChange={e => setWord(e.target.value)} /><Button type="submit" disabled={!word.trim()} loading={busy}>추가하기</Button></form><div className="ds-actions"><Button onClick={async () => { setBusy(true); try { setSuggestions(await onSuggest(group)); } finally { setBusy(false); } }}>추천 단어 불러오기</Button></div>{suggestions?.length === 0 && <Banner>추천할 단어가 없습니다. 직접 입력하세요.</Banner>}<div className="ds-chips">{suggestions?.map(w => <Button key={w} size="sm" onClick={() => void add(w, 'suggested')}>{w} 추가하기</Button>)}</div>{!!suggestions?.length && <Button onClick={async () => { setBusy(true); try { for (const w of suggestions) { if (await onAdd(w, group, 'suggested')) setSuggestions(s => s?.filter(v => v !== w) ?? null); } } finally { setBusy(false); } }}>추천 단어 모두 추가하기</Button>}</fieldset>}
    </div>}
  </section>;
}
