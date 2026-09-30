'use client';
import { useEffect, useState } from 'react';
import { Button, Card } from '@/components/ds';
import { QueueCard } from './QueueCard';
import { getNextLabel } from '@/lib/api/label';
import { displayError } from '@/lib/api/errors';
import type { Overview, QueueItem, ReviewMode } from '@/lib/types';

export type QueueProps = { sid: string; version?: string; readonly?: boolean; overview: Overview; mode?: ReviewMode; round?: number; onSubmitted: () => void };
export function Queue({ sid, version, readonly = false, overview, mode = 'escalate', round, onSubmitted }: QueueProps) {
  const [request, setRequest] = useState<{after?: string; count: number}>({count: 0});
  const [result, setResult] = useState<{item: QueueItem | null; message: string | null} | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    getNextLabel(sid, {mode, round, after: request.after, version}).then(value => {
      if (active) { setResult(value); setError(''); }
    }).catch(e => { if (active) setError(displayError(e)); });
    return () => { active = false; };
  }, [sid, version, mode, round, request]);
  return <div className="space-y-4">
    {mode === 'escalate' && <p>남은 {overview.queue.total.toLocaleString('ko-KR')}건 · 예상 {Math.ceil(overview.queue.estimatedSeconds / 60).toLocaleString('ko-KR')}분</p>}
    {error ? <Card><p role="alert">{error}</p><Button onClick={() => { setError(''); setRequest(r => ({...r, count:r.count + 1})); }}>다시 불러오기</Button></Card> : result ? result.item ?
      <QueueCard sid={sid} version={version} item={result.item} mode={mode} labeler="human" readonly={readonly} onSubmitted={onSubmitted} onNext={after => { setResult(null); setRequest(r => ({after, count:r.count + 1})); }}/>
      : <Card><p role="status">{result.message || '사람이 볼 문서가 없습니다.'}</p><Button onClick={() => {setResult(null); setRequest(r => ({count:r.count + 1}));}}>처음부터 다시 확인</Button></Card>
      : <p role="status">문서를 불러오는 중…</p>}
    <Card><h3 className="ds-t-card">키보드</h3><p>A = 대상 경험 · 1~6 = 6차원 · S = 상황 · Enter = 제출 = 저장 · → = 건너뛰기</p><p className="ds-t-caption">판정 카드 안에서만 동작합니다. 입력칸 · 열린 패널 · 팝오버에서는 단축키를 끕니다.</p></Card>
    {mode === 'escalate' && <Card><h3 className="ds-t-card">큐 사유</h3><p>등급 불일치 {overview.queue.byReason.grade_mismatch ?? 0}건 · 판정 실패 {overview.queue.byReason.labeler_failed ?? 0}건</p></Card>}
  </div>;
}
