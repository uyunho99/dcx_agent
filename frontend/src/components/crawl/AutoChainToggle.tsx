'use client';
import { useState } from 'react';
import { setAutoChain } from '@/lib/api/crawl';
import { displayError } from '@/lib/api/errors';
import { useSessionStore } from '@/stores/useSessionStore';
import { Banner } from '../ds';

type AutoChainStatus = { stage?: string; state?: string; error?: string };
export function autoChainLabel(status: AutoChainStatus | undefined) {
  if (!status?.stage) return '';
  const stage = status.stage === 'prep' ? '전처리' : '라벨링';
  if (status.state === 'failed') return `자동 ${stage} 시작 실패: ${status.error ?? ''}`;
  return `자동으로 ${stage}를 시작했습니다.`;
}

/** Crawl → preprocessing → labeling without waiting for button presses. */
export function AutoChainToggle({ sid, disabled }: { sid: string; disabled?: boolean }) {
  const sd = useSessionStore(s => s.sd) as (Record<string, unknown> & { autoChain?: boolean; autoChainStatus?: AutoChainStatus }) | null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const on = !!sd?.autoChain;
  async function toggle(next: boolean) {
    setBusy(true); setError('');
    try {
      await setAutoChain(sid, next);
      const store = useSessionStore.getState();
      if (store.sd) store.setSession({ sd: { ...store.sd, autoChain: next } });
    } catch (e) { setError(displayError(e)); }
    finally { setBusy(false); }
  }
  const note = autoChainLabel(sd?.autoChainStatus);
  return <div className="space-y-2">
    <label className="flex items-center gap-2"><input type="checkbox" checked={on} disabled={disabled || busy} onChange={e => void toggle(e.target.checked)}/>크롤링이 끝나면 전처리 · 라벨링(GPT, 블로그 · 카페 먼저)까지 자동으로 시작</label>
    {note && <p className="ds-t-caption">{note}</p>}
    {error && <Banner tone="danger">{error}</Banner>}
  </div>;
}
