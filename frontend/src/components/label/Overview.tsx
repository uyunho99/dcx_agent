'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, InsightCard } from '@/components/ds';
import { KappaTable } from './KappaTable';
import { LabelerProgress } from './LabelerProgress';
import { controlTarget, type WorkerAction } from './workerControls';
import { LevelBadge } from './LevelBadge';
import { controlLabeler, setLabelMode, startLabel } from '@/lib/api/label';
import { getModels } from '@/lib/api/train';
import { displayError } from '@/lib/api/errors';
import { pickNowCard } from '@/lib/logic/nowCard';
import type { EvidenceLevel, ModelMetadata, Overview as OverviewData } from '@/lib/types';

export function Overview({sid, version, overview: o, readonly = false, onRefresh, onNavigate}: {sid: string; version?: string; overview: OverviewData; readonly?: boolean; onRefresh: () => void; onNavigate: (target: 'queue' | 'audit' | 'definitions' | 'training') => void}) {
  const [mode, setMode] = useState(o.mode);
  const [modelId, setModelId] = useState(o.modelId ?? '');
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const workers = useRef<HTMLDivElement>(null);
  const now = pickNowCard(o);
  useEffect(() => {
    if (o.started) return;
    let active = true;
    getModels(sid, version).then(result => {if (active) setModels(result.models);}).catch(e => {if (active) setError(displayError(e));});
    return () => {active = false;};
  }, [sid, version, o.started]);
  async function start() {
    if (readonly || lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await setLabelMode(sid, {mode, modelId:mode === 'model' ? modelId : null}, version); await startLabel(sid, version); onRefresh(); }
    catch(e) {setError(displayError(e)); onRefresh();}
    finally {lock.current = false; setBusy(false);}
  }
  async function control(labeler: 'jev' | 'gpt' | 'infer', action: WorkerAction) {
    if (readonly || lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {await controlLabeler(sid, labeler, action, version); onRefresh();}
    catch(e) {setError(displayError(e));}
    finally {lock.current = false; setBusy(false);}
  }
  return <div className="space-y-6">
    {error && <p role="alert">{error}</p>}
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">{!o.started ? <Card className="space-y-4"><p className="ds-eyebrow">지금 할 일</p><h2 className="ds-t-insight">라벨링을 시작하세요</h2>
        <fieldset disabled={busy || readonly}><legend>라벨링 방식</legend><label className="mr-4"><input type="radio" name="label-mode" checked={mode === 'llm'} onChange={() => setMode('llm')}/> LLM 라벨</label><label><input type="radio" name="label-mode" checked={mode === 'model'} disabled={!models.some(m => m.selectable !== false)} onChange={() => setMode('model')}/> 분류 모델</label>
        {mode === 'model' && <label className="ds-field">모델 선택<select className="ds-inp" value={modelId} onChange={e => setModelId(e.target.value)}><option value="">모델을 선택하세요</option>{models.map(m => <option key={m.modelId} value={m.modelId} disabled={m.selectable === false}>{m.modelId} · {String(m.bk ?? '')} · {String(m.oneLiner ?? '')}{m.reason ? ` · ${m.reason}` : ''}</option>)}</select></label>}
        {!models.some(m => m.selectable !== false) && <p className="ds-t-caption">사용할 수 있는 분류 모델이 없습니다.</p>}</fieldset>
        <p>{now.body}</p><Button variant="primary" loading={busy} disabled={readonly || (mode === 'model' && !models.some(m => m.modelId === modelId && m.selectable !== false))} onClick={() => void start()}>라벨링 시작</Button>
      </Card> : <InsightCard eyebrow="지금 할 일" insight={now.title} interpretation={<><p>{now.body}</p><p>지난 접속 이후 새로 판정 {o.changes.judged.toLocaleString('ko-KR')}건 · 채택 {o.changes.accepted.toLocaleString('ko-KR')}건 · 큐에 쌓인 문서 {o.changes.queued.toLocaleString('ko-KR')}건</p></>} evidence={[{label:'불일치율',value:`${(o.mismatchRate * 100).toFixed(1)}%`}]} nextAction={now.action && <Button variant="primary" onClick={() => {const target = now.action!.target; if(target === 'workers') {workers.current?.focus(); workers.current?.scrollIntoView({behavior:'smooth'});} else if(target !== 'start') onNavigate(target);}}>{now.action.label}</Button>}/>}</div>
      <Card><h2 className="ds-t-card">합친 결과</h2><dl className="space-y-2"><dt>합친 문서</dt><dd>{o.merged.toLocaleString('ko-KR')} / {o.total.toLocaleString('ko-KR')}건</dd><dt>채택</dt><dd>{o.accepted.toLocaleString('ko-KR')}건</dd><dt>불일치율</dt><dd>{(o.mismatchRate * 100).toFixed(1)}%</dd><dt>검수 큐</dt><dd>{o.queue.total.toLocaleString('ko-KR')}건 · 예상 {Math.ceil(o.queue.estimatedSeconds / 60)}분</dd></dl></Card>
    </div>
    <div ref={workers} tabIndex={-1}><Card className="space-y-4"><h2 className="ds-t-card">전량 판정</h2><p className="ds-t-caption">화면을 닫아도 계속됩니다.</p><div className="grid gap-6 md:grid-cols-2">{Object.entries(o.progress).map(([name, progress]) => <div key={name} className="space-y-2"><LabelerProgress key={name} name={name === 'jev' ? 'Jev' : name === 'gpt' ? 'GPT' : name === 'infer' ? '분류 모델' : '감시'} progress={progress} busy={busy} onControl={!readonly && controlTarget(name, o.mode) ? action => void control(controlTarget(name, o.mode)!, action) : undefined}/>{progress.state === 'running' && progress.estimate?.seconds != null && <p className="ds-t-caption">예상 완료 · {new Date(Date.now() + progress.estimate.seconds * 1000).toLocaleString('ko-KR')}</p>}{name === 'jev' && <p className="ds-t-caption">예상 Jev 비용 · 금액 추정은 아직 제공되지 않습니다.{typeof progress.estimate?.jevTokens === 'number' && ` 예상 입력 ${progress.estimate.jevTokens.toLocaleString('ko-KR')}토큰`}</p>}</div>)}</div></Card></div>
    <Card><h2 className="ds-t-card">등급 분포</h2><div className="flex flex-wrap gap-6">{(['core','supporting','non'] as EvidenceLevel[]).map(level => <p key={level}><LevelBadge level={level}/> {o.levelDistribution[level].toLocaleString('ko-KR')}건</p>)}</div></Card>
    <Card><KappaTable audit={o.audit.at(-1)?.kappaAI} jev={o.labelerAccuracy.jev} gpt={o.labelerAccuracy.gpt}/></Card>
  </div>;
}
