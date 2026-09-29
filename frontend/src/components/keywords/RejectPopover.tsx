'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, ChoiceChips, Input, Select } from '@/components/ds';
import type { Destination, Rejection } from '@/lib/api/keywords';
import { groupKey, groupLabel } from './taxonomy';
export function RejectPopover({ initial, groups, moving, onConfirm, onCancel }: { initial?: Rejection | null; groups: Destination[]; moving: boolean; onConfirm: (reject: Rejection, destination?: Destination) => Promise<void>; onCancel: () => void }) {
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => { const frame = requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('button, input, select')?.focus()); return () => cancelAnimationFrame(frame); }, []);
  const [tags, setTags] = useState(initial?.tags ?? []); const [note, setNote] = useState(initial?.note ?? '');
  const [target, setTarget] = useState(initial?.to ? groupKey(initial.to) : ''); const [busy, setBusy] = useState(false);
  const needsMove = moving || tags.includes('misclassified');
  const destination = groups.find(g => groupKey(g) === target);
  async function submit() { if (busy || (needsMove && !destination)) return; setBusy(true); try { await onConfirm({ tags, note }, needsMove ? destination : undefined); } catch { /* The page displays the API error; preserve this form for retry. */ } finally { setBusy(false); } }
  return <form ref={form} onSubmit={event => { event.preventDefault(); void submit(); }} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void submit(); } }}>
    <fieldset disabled={busy} className="space-y-3">
      {!moving && <><p className="ds-t-caption">사유를 고르면 다음 라운드에 반영됩니다.</p><ChoiceChips label="거절 사유" multiple value={tags} onChange={setTags} options={[{ value: 'irrelevant', label: '관련성 낮음' }, { value: 'common', label: '흔함' }, { value: 'sentence', label: '문장형' }, { value: 'misclassified', label: '오분류' }]} /><Input label="메모 (선택)" value={note} onChange={e => setNote(e.target.value)} /></>}
      {needsMove && <Select label="옮길 하위 카테고리" required value={target} onChange={e => setTarget(e.target.value)}><option value="">분류 선택</option>{groups.map(g => <option key={groupKey(g)} value={groupKey(g)}>{groupLabel(g)}</option>)}</Select>}
      <p className="ds-t-caption">Enter 저장 · Esc 닫기</p><div className="ds-actions"><Button size="sm" onClick={onCancel}>취소하기</Button><Button type="submit" size="sm" loading={busy} disabled={needsMove && !destination}>{moving ? '이동하기' : '거절하기'}</Button></div>
    </fieldset>
  </form>;
}
