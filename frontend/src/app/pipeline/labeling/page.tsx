'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSessionStore } from '@/stores/useSessionStore';
import { useVersion } from '@/components/versions/VersionProvider';
import { RestartVersion } from '@/components/versions/StageVersion';
import { Badge, Banner, Button, Tabs } from '@/components/ds';
import { Overview } from '@/components/label/Overview';
import { useLabelSeen } from '@/components/label/useLabelSeen';
import { Queue } from '@/components/label/Queue';
import { Audit } from '@/components/label/Audit';
import { getEvidenceStatus } from '@/lib/api/evidence';
import { getLabelOverview } from '@/lib/api/label';
import { useStageCompletionRefresh } from '@/components/versions/useStageCompletionRefresh';
import { labelCompletionKey } from '@/lib/refreshSessionAfterStage';
import { displayError } from '@/lib/api/errors';
import type { LegacyOverview, Overview as OverviewData } from '@/lib/types';

export default function LabelingPage() {
  const sid = useSessionStore(s => s.sid);
  const view = useVersion();
  if (!sid) return <p role="status">세션을 먼저 선택하세요.</p>;
  return <LabelingScreen key={`${sid}:${view.version}`} sid={sid}/>;
}
function LabelingScreen({sid}: {sid: string}) {
  const router = useRouter();
  const {version, readonly, session} = useVersion();
  const [tab, setTab] = useState('overview');
  const [overview, setOverview] = useState<OverviewData | LegacyOverview | null>(null);
  useStageCompletionRefresh(labelCompletionKey(overview));
  const [error, setError] = useState('');
  const [seenError, setSeenError] = useState('');
  const [irrelevant, setIrrelevant] = useState(0);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(n => n + 1), []);
  useEffect(() => {
    let active = true;
    let pending = false;
    async function read() {
      if (pending) return;
      pending = true;
      try {const result = await getLabelOverview(sid, version); if(active) {setOverview(result); setError('');}}
      catch(e) {if(active) setError(displayError(e));}
      finally {pending = false;}
    }
    void read();
    const timer = setInterval(() => void read(), 5000);
    return () => {active = false; clearInterval(timer);};
  }, [sid, version, revision]);
  useEffect(() => {
    let active = true;
    void getEvidenceStatus(sid, version).then(result => {
      const count = result.stage7?.irrelevant;
      if (active) setIrrelevant(typeof count === 'number' && Number.isFinite(count) && count > 0 ? count : 0);
    }).catch(() => { if (active) setIrrelevant(0); });
    return () => { active = false; };
  }, [sid, version, revision]);
  // Start overview independently; seen records visits without changing displayed server counts.
  useLabelSeen(sid, version, readonly, setSeenError);
  return <main className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="ds-eyebrow">4단계 · 라벨링</p><h1 className="ds-t-screen">엇갈린 문서를 한 건씩 정합니다</h1><p>채택 라벨은 감사로 확인하고, 제출한 판정은 바로 저장합니다.</p></div><div className="flex flex-wrap items-center gap-3">{overview && !('legacy' in overview) && overview.started && <Badge>{overview.mode === 'llm' ? 'LLM 라벨' : '분류 모델'} · 방식 잠금</Badge>}<RestartVersion stage="stage4" label="4단계부터 다시" disabled={readonly}/></div></header>
    {irrelevant > 0 && <Banner tone="info">7단계에서 무관 판정 {irrelevant}건 — 4단계 재점검 참고</Banner>}
    {seenError && <p role="alert">방문 시각을 기록하지 못했습니다. {seenError}</p>}
    {error && <div role="alert"><p>{error}</p><Button onClick={refresh}>다시 불러오기</Button></div>}
    {!overview ? <p role="status">라벨링 현황을 불러오는 중…</p> : 'legacy' in overview ? <p>{overview.message}</p> : <Tabs label="라벨링" value={tab} onChange={setTab} items={[
      {value:'overview', label:'개요', content:tab === 'overview' && <Overview sid={sid} version={version} readonly={readonly} overview={overview} onRefresh={refresh} onNavigate={target => {if(target === 'training') router.push('/pipeline/training'); else setTab(target === 'definitions' ? 'audit' : target);}}/>},
      {value:'queue', label:'검수 큐', count:overview.queue.total, content:tab === 'queue' && <Queue sid={sid} version={version} readonly={readonly} overview={overview} onSubmitted={refresh}/>},
      {value:'audit', label:'감사', content:tab === 'audit' && <Audit sid={sid} version={version} readonly={readonly} overview={overview} oneLiner={session?.projectContext?.oneLiner} onRefresh={refresh}/>},
    ]}/>}
  </main>;
}
