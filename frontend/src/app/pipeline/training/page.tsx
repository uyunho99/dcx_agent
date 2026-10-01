'use client';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Banner, Button, Card, ProgressBar } from '@/components/ds';
import { useVersion } from '@/components/versions/VersionProvider';
import { useStageCompletionRefresh } from '@/components/versions/useStageCompletionRefresh';
import { LevelBadge } from '@/components/label/LevelBadge';
import { ModelRepository } from '@/components/train/ModelRepository';
import { TrainingResult } from '@/components/train/TrainingResult';
import { driftMessage, exportAndAdvance, number, record, shouldPollTraining, trainingLabels, trainingState } from '@/components/train/trainingView';
import { exportTraining, getModels, getTrainingStatus, startTraining } from '@/lib/api/train';
import { getLabelOverview } from '@/lib/api/label';
import { patchSession } from '@/lib/api/context';
import { displayError } from '@/lib/api/errors';
import type { ModelMetadata, Overview, TrainingStatus } from '@/lib/types';
import { useSessionStore } from '@/stores/useSessionStore';

export default function TrainingPage() {
  const sid = useSessionStore(s => s.sid);
  const view = useVersion();
  if (!sid) return <Card>세션을 먼저 선택하세요.</Card>;
  return <TrainingScreen key={`${sid}:${view.version ?? ''}`} sid={sid} version={view.version} readonly={view.readonly || !!view.conflict} />;
}

function TrainingScreen({ sid, version, readonly }: { sid: string; version?: string; readonly: boolean }) {
  const router = useRouter();
  const {refreshSessionAfterStage} = useVersion();
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  useStageCompletionRefresh(typeof status?.training.exportRef === 'string' ? status.training.exportRef : null);
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const lock = useRef(false);
  const mounted = useRef(false);
  const generation = useRef(0);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      const epoch = generation.current;
      let keepPolling = true;
      try {
        const [nextStatus, repository, labels] = await Promise.all([getTrainingStatus(sid, version), getModels(sid, version), getLabelOverview(sid, version)]);
        if (active && epoch === generation.current) {
          keepPolling = shouldPollTraining(nextStatus);
          setStatus(nextStatus); setModels(repository.models);
          setOverview('legacy' in labels ? null : labels); setLoadError('');
        }
      } catch (e) { if (active && epoch === generation.current) setLoadError(displayError(e)); }
      finally { if (active && epoch === generation.current && keepPolling) timer = setTimeout(read, 5000); }
    }
    void read();
    return () => { active = false; clearTimeout(timer); };
  }, [sid, version, retry]);

  const state = status ? trainingState(status) : { busy: false, ready: false, error: '', monitorNotice: '' };
  const blocked = readonly || !!status?.readonly || busy || state.busy || !status || !!loadError;
  const model = models.find(m => m.modelId === status?.training.modelId);
  const train = status?.workers?.find(w => w.kind === 'train');
  const divergence = number(record(status?.training.monitor).monitorDivergence) ?? number(status?.stage5?.monitorDivergence);
  const {count: trainable, empty} = trainingLabels(overview);
  const drift = driftMessage(!!status?.training.modelId, divergence);

  async function start(parent: string | null = null) {
    if (blocked || empty || lock.current) return;
    lock.current = true; generation.current++; setBusy(true); setError('');
    try {
      const worker = await startTraining(sid, parent, version);
      if (mounted.current) { setStatus({training: {runId: worker.runId}, workers: [worker]}); setRetry(n => n + 1); }
    } catch (e) { if (mounted.current) setError(displayError(e)); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  async function save(withoutModel: boolean) {
    if (blocked || lock.current || (!withoutModel && !state.ready)) return;
    lock.current = true; generation.current++; setBusy(true); setError('');
    try {
      await exportAndAdvance(async () => {
        const result = await exportTraining(sid, withoutModel, version);
        if (result.exportRef && mounted.current) await refreshSessionAfterStage();
        return result;
      }, () => patchSession(sid, {step: 'clustering'}, version), () => {
        if (!mounted.current) return;
        const store = useSessionStore.getState();
        store.setSession({step: 'clustering', ...(store.sd ? {sd: {...store.sd, step: 'clustering'}} : {})});
        router.push('/pipeline/clustering');
      });
    } catch (e) { if (mounted.current) setError(displayError(e, '저장하지 못했습니다. 다시 시도하세요.')); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  }

  return <div className="space-y-6"><Button variant="quiet" onClick={() => router.push('/pipeline/labeling')}>← 라벨링으로</Button><header className="flex flex-wrap justify-between gap-4"><div className="space-y-2"><p className="ds-eyebrow">5단계 · 학습</p><h1 className="ds-t-section">합의 라벨로 분류 모델을 만듭니다</h1><p className="ds-t-body">벡터 위 작은 모델 4개(앙상블)가 태그를 예측하고, 등급은 규칙으로 계산합니다. 다음 세션은 이 모델로 LLM 없이 라벨링할 수 있습니다.</p></div><div className="ds-actions"><Button disabled={blocked} onClick={() => void save(true)}>모델 없이 내보내기</Button><Button variant={state.ready && model ? 'secondary' : 'primary'} disabled={blocked || empty} onClick={() => void start()}>{model ? '다시 학습' : '학습 시작'}</Button></div></header>
    {(readonly || status?.readonly) && <Banner>읽기 전용 버전입니다.</Banner>}
    {loadError && <Banner tone="danger" actions={<Button onClick={() => setRetry(n => n + 1)}>다시 확인하기</Button>}>{loadError}</Banner>}
    {(error || state.error) && <Banner tone="danger">{error || state.error}</Banner>}
    {state.monitorNotice && <Banner tone="warning">{state.monitorNotice}</Banner>}
    {drift && <Banner tone="warning">{drift}</Banner>}
    {!status ? <Card><p role="status">학습 정보를 불러오는 중…</p></Card> : state.busy ? <Card className="space-y-4"><h2 className="ds-t-card">학습 · 추론 진행 중</h2><ProgressBar label="전체 작업 진행" value={number(train?.progress) === undefined ? undefined : train!.progress * 100} /><div className="grid gap-4 md:grid-cols-4">{['MLP 1', 'MLP 2', 'MLP 3', '선형 1'].map(name => <div key={name}><h3 className="ds-t-label">{name}</h3><ProgressBar label={`${name} 학습 진행`} value={train?.state === 'done' ? 100 : undefined} /></div>)}</div><p className="ds-t-caption">멤버별 진행률은 확인 중입니다. 학습 후 전체 문서를 추론합니다.</p></Card> : state.ready && model ? <TrainingResult model={model} disabled={blocked} onExport={() => void save(false)} /> : <Card className="space-y-3"><h2 className="ds-t-card">학습 준비</h2><p>{empty ? '학습할 라벨이 없습니다. 라벨링을 먼저 끝내세요.' : '합의로 채택한 라벨과 사람이 판정한 라벨로 학습합니다.'}</p>{overview && <p>학습할 라벨 {trainable?.toLocaleString('ko-KR')}건 · 검수 대기 {overview.queue.total.toLocaleString('ko-KR')}건</p>}<p className="ds-t-caption">정확한 학습 건수는 학습 후 확인할 수 있습니다. 임베딩에 실패한 문서는 학습에서 제외됩니다.</p></Card>}
    <p className="ds-t-caption flex flex-wrap items-center gap-2">내보내기에는 <LevelBadge level="core" />와 <LevelBadge level="supporting" /> 문서가 포함됩니다.</p>
    <ModelRepository models={models} current={typeof status?.training.modelId === 'string' ? status.training.modelId : undefined} disabled={blocked || empty} onTrain={id => void start(id)} />
  </div>;
}
