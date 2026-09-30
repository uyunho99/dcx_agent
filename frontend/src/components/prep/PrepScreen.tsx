'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Banner, Button, Card, ProgressBar, Skeleton } from '@/components/ds';
import { useDirty } from '@/components/DirtyProvider';
import { useVersion } from '@/components/versions/VersionProvider';
import { getVersionSession } from '@/lib/api/versions';
import { getCrawlStatus } from '@/lib/api/crawl';
import { patchSession } from '@/lib/api/context';
import { displayError } from '@/lib/api/errors';
import { getPrepStatus, runPrep, savePrepConfig } from '@/lib/api/prep';
import type { PrepConfig, PrepStatus } from '@/lib/types';
import { useSessionStore } from '@/stores/useSessionStore';
import { PrepSettings } from './PrepSettings';
import { PrepResult } from './PrepResult';
import { prepConfig, prepEditLock, prepEstimate, prepPhase, prepView, type PrepSession } from './prep';
import { executePrep } from './workflow';
import './prep.css';
import { RestartVersion } from '@/components/versions/StageVersion';
import { embedderLabel } from '@/lib/logic/browserQa';

export function PrepScreen({ sid }: { sid: string }) {
  const { version, readonly } = useVersion();
  const router = useRouter();
  const { register, confirmNavigation } = useDirty();
  const [editLock, setEditLock] = useState<string | null>(null);
  const [config, setConfig] = useState<PrepConfig | null>(null);
  const [status, setStatus] = useState<PrepStatus | null>(null);
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [sourceCount, setSourceCount] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);
  const [pollRetry, setPollRetry] = useState(0);
  const lock = useRef(false);
  const mounted = useRef(true);
  const view = prepView(status);
  const paused = status?.status === 'paused';
  const disabled = busy || view.running || paused || readonly || !!editLock;
  const valid = !!config && Number.isInteger(config.minBodyChars) && config.minBodyChars >= 0;

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    register('prep', dirty);
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => { register('prep', false); window.removeEventListener('beforeunload', warn); };
  }, [dirty, register]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getVersionSession(sid, version), getPrepStatus(sid, version)]).then(([session, current]) => {
      if (cancelled) return;
      const saved = session.data as PrepSession;
      setEditLock(prepEditLock(saved));
      setConfig(prepConfig(saved, current.status !== 'running' && current.status !== 'paused', current.config));
      setCollectionId(saved.collectionId ?? null);
      setStatus(current); setError('');
      if (!prepEditLock(saved) && saved.drafts?.prep?.config && current.status !== 'running' && current.status !== 'paused') setNotice('임시 저장한 설정을 불러왔습니다. 실행하면 결과에 반영됩니다.');
    }).catch(cause => { if (!cancelled) setError(displayError(cause, '전처리 설정을 불러오지 못했습니다. 다시 확인하세요.')); });
    // Crawl reporting is optional; a reporting failure must not block preparation.
    if (!readonly) void getCrawlStatus(sid).then(crawl => {
      if (!cancelled) setSourceCount(crawl.report?.totals.doc_count ?? null);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [sid, version, readonly, reload]);

  useEffect(() => {
    if ((!view.running && !paused) || readonly) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const fresh = await getPrepStatus(sid, version);
        if (cancelled) return;
        setStatus(fresh); setPollError('');
        if (fresh.status !== 'running' && fresh.status !== 'paused') return;
      } catch (cause) {
        if (cancelled) return;
        setPollError(displayError(cause, '진행 상태를 확인하지 못했습니다. 연결 후 다시 확인합니다.'));
      }
      if (!cancelled) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [sid, version, view.running, paused, readonly, pollRetry]);

  const act = useCallback(async (task: () => Promise<void>) => {
    if (lock.current || readonly) return;
    lock.current = true; setBusy(true); setError(''); setNotice('');
    try { await task(); }
    catch (cause) { if (mounted.current) setError(displayError(cause, '저장하지 못했습니다. 입력은 그대로 있습니다. 다시 시도하세요.')); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  }, [readonly]);

  async function saveDraft() {
    if (!config || disabled || !valid) return;
    await act(async () => {
      await patchSession(sid, { drafts: { prep: { config } } }, version);
      if (mounted.current) { setDirty(false); setNotice('설정을 임시 저장했습니다. 실행하면 결과에 반영됩니다.'); }
    });
  }
  async function run() {
    if (!config || disabled || !valid || !collectionId) return;
    await act(async () => {
      try {
        const result = await executePrep(config, {
          save: current => savePrepConfig(sid, current, version),
          run: () => runPrep(sid, version),
          clearDraft: () => patchSession(sid, { drafts: { prep: null } }, version),
        });
        if (!mounted.current) return;
        setStatus(result.status); setDirty(false); setPollError('');
        if (!result.draftCleared) setNotice('전처리는 시작했지만 임시 설정을 정리하지 못했습니다. 임시 저장으로 현재 설정을 다시 저장하세요.');
      } catch (cause) {
        // PUT config invalidates the previous result even if POST run fails.
        try { const fresh = await getPrepStatus(sid, version); if (mounted.current) setStatus(fresh); }
        catch { if (mounted.current) setStatus(null); }
        throw cause;
      }
    });
  }
  async function next() {
    if (!view.canNext || busy || readonly || !confirmNavigation()) return;
    await act(async () => {
      await patchSession(sid, { step: 'labeling' }, version);
      if (!mounted.current) return;
      register('prep', false); setDirty(false);
      useSessionStore.getState().setSession({ step: 'labeling' });
      router.push('/pipeline/labeling');
    });
  }

  const settings = config && <PrepSettings config={config} disabled={disabled} replacements={view.report?.boilerplate_replaced} onChange={value => { setConfig(value); setDirty(true); setNotice(''); }} />;
  const estimate = prepEstimate(view.report);
  return <div className="prep-screen">
    <header className="prep-header"><div><p className="ds-eyebrow">3단계 · 전처리 · 임베딩</p><h1 className="ds-t-section">라벨링에 쓸 문서와 벡터를 만듭니다</h1><p className="ds-t-body">규칙은 명백한 광고 · 중복 · 너무 짧은 글만 뺍니다. 대상과 관련 있는지는 4단계에서 판단합니다.</p></div><div className="ds-actions"><RestartVersion stage="stage3" label="3단계부터 다시" disabled={readonly}/><Button disabled={!config || disabled || !valid} onClick={() => void saveDraft()}>임시 저장</Button><Button variant={view.canNext ? 'secondary' : 'primary'} disabled={!config || disabled || !valid || !collectionId} loading={busy} onClick={() => void run()}>{view.resumable ? '이어서 진행' : view.report || status?.status === 'failed' || status?.status === 'cancelled' ? '다시 실행' : '전처리 실행'}</Button></div></header>
    {error && <Banner tone="danger" actions={!config ? <Button onClick={() => setReload(value => value + 1)}>다시 확인하기</Button> : undefined}>{error}</Banner>}
    {editLock && <Banner tone="warning">{editLock}</Banner>}
    {notice && <Banner tone="success">{notice}</Banner>}
    {!config && !error && <div role="status" aria-label="전처리 설정을 불러오는 중"><Skeleton height={240} /></div>}
    {config && !collectionId && <Banner tone="warning" actions={<Button onClick={() => { if (confirmNavigation()) router.push('/pipeline/crawling'); }}>크롤링으로</Button>}>수집본을 먼저 준비하세요.</Banner>}
    {pollError && <Banner tone="warning" actions={<Button onClick={() => setPollRetry(value => value + 1)}>다시 확인하기</Button>}>{pollError}</Banner>}
    {(view.running || paused) && <Card className="space-y-4"><h2 className="ds-t-card">{paused ? '전처리가 일시 정지되었습니다' : '전처리 진행 중'}</h2><p role="status">{prepPhase(status?.detail)}{view.running ? ' · 처리 중' : ''}</p><ProgressBar label="전처리 진행률" value={status?.progress} max={1} /><p className="ds-t-caption">필터 → 토큰 → 임베딩 순서로 처리합니다. 완료된 작업은 이어서 사용합니다.</p></Card>}
    {status?.status === 'interrupted' && <Banner tone="warning">작업이 중단되었습니다. 같은 규칙으로 이어서 진행하면 완료된 작업을 재사용합니다.</Banner>}
    {status?.status === 'cancelled' && <Banner tone="warning">전처리가 취소되었습니다. 설정을 확인하고 다시 실행하세요.</Banner>}
    {status?.status === 'failed' && <Banner tone="danger">{status.error?.kind === 'kiwi_unavailable' ? '형태소 분석기를 불러오지 못했습니다. 설치 후 이어서 진행하세요.' : status.error?.kind === 'embedder_unconnected' ? '임베딩 API가 연결되지 않았습니다. 연결하거나 내부용 설정에서 가짜 임베더로 바꾸세요.' : status.error?.message ?? '전처리에 실패했습니다. 설정을 확인하고 다시 실행하세요.'}</Banner>}
    {status?.status === 'done' && !view.report && <Banner tone="warning" actions={<Button onClick={() => void act(async () => { const fresh = await getPrepStatus(sid, version); if (mounted.current) setStatus(fresh); })}>다시 확인하기</Button>}>완료된 결과를 불러오지 못했습니다. 다시 확인하거나 실행하세요.</Banner>}
    {view.report && status && <PrepResult report={view.report} status={status} busy={busy || readonly} onNext={() => void next()} />}
    {config && <div className="prep-grid"><div>{editLock ? <><Button disabled>규칙 수정하고 다시 실행</Button>{settings}</> : view.report ? <details><summary className="prep-settings-summary">규칙 수정하고 다시 실행</summary><p className="ds-t-caption mb-4">결과는 마지막 실행 기준입니다. 수정한 규칙은 다시 실행한 뒤 반영됩니다.</p>{settings}</details> : settings}</div><aside className="space-y-6"><Card className="space-y-4"><h2 className="ds-t-card">만들어지는 것</h2><dl className="ds-kv"><dt>원문 정제본</dt><dd>라벨러 · 임베딩 입력</dd><dt>형태소 토큰</dt><dd>Kiwi · 문장부호 삭제</dd><dt>임베딩</dt><dd>{embedderLabel(config.embedder)} · 전량 1회</dd></dl><p className="ds-t-caption">같은 수집본과 같은 규칙이면 새 버전에서도 다시 만들지 않습니다.</p></Card><Card className="space-y-3"><p className="ds-eyebrow">예상</p><p className="ds-t-section">{estimate ? `${estimate.original.toLocaleString('ko-KR')}건 → 약 ${estimate.after.toLocaleString('ko-KR')}건` : sourceCount !== null ? `수집 문서 ${sourceCount.toLocaleString('ko-KR')}건` : '수집 건수 확인 전'}</p><p className="ds-t-caption">{estimate ? `직전 실행 기준 · 벡터 저장 약 ${(estimate.storageBytes / 1024 ** 3).toFixed(2)}GB` : '통과 건수와 저장량은 실행 후 확인할 수 있습니다.'}</p><p className="ds-t-caption">임베딩 예상 시간은 아직 제공되지 않습니다.</p><div className="ds-nextact"><span className="ds-t-label">규칙을 확인하고 실행하세요</span></div></Card></aside></div>}
  </div>;
}
