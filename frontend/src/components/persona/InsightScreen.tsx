'use client';
import { useEffect, useRef, useState } from 'react';
import * as api from '@/lib/api/insight';
import { displayError } from '@/lib/api/errors';
import type { InsightConcept, InsightItem, InsightResponse, InsightTarget } from '@/lib/types';
import ChatPanel from '../ChatPanel';
import { Button } from '../ds/Button';
import { useVersion } from '../versions/VersionProvider';
import { useStageCompletionRefresh } from '../versions/useStageCompletionRefresh';
import { Radar, radarAxes, type RadarValues } from './Radar';
import { OpportunityBars } from './OpportunityBars';
import { JourneyTable } from './JourneyTable';
import { RevisionList } from './RevisionList';
import { createInsightActions } from './insightActions';
import { contextLabels } from '@/lib/contextLabels';
import { displayValue } from './personaView';

const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = displayValue;
const number = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : null;
function radarValues(value: unknown): RadarValues {
 const row = record(value); const raw = record(row.raw); const percentile = record(row.percentile);
 return Object.fromEntries(Object.keys(radarAxes).map(axis => [axis,{raw:number(raw[axis] ?? record(row[axis]).raw),percentile:number(percentile[axis] ?? record(row[axis]).percentile)}])) as RadarValues;
}
function sourceLocation(value: unknown): string {
 const location = record(value);
 if (location.field === 'title') return '제목';
 if (location.field === 'body') return '본문';
 if (location.field === 'comment' || location.field === 'comments') return typeof location.idx === 'number' ? `댓글 ${location.idx + 1}` : '댓글';
 return '위치 미상';
}
function channelLabel(value: unknown): string {
 return contextLabels.channels[value as keyof typeof contextLabels.channels] ?? text(value);
}
export function ConceptDetail({concept}: {concept: InsightConcept}) {
 return <section aria-label="경험 디자인 컨셉" className="ds-card space-y-5">
  <h2 className="ds-t-card">01 PERSONA <span style={{color:'var(--danger)'}}>🔴 합성값</span></h2><p>{text(record(concept.persona_profile).text ?? concept.persona_profile)}</p><p>{concept.basis}</p>
  <h2 className="ds-t-card">02 Pain Points</h2>{concept.pain_points.map((point,index) => <blockquote key={index}><p>{text(point.quote)}</p><footer>{channelLabel(point.channel)} · {sourceLocation(point.location)} · Context {text(point.context_id)}</footer></blockquote>)}
  <h2 className="ds-t-card">03 JOURNEY</h2><JourneyTable rows={concept.journey}/>
  <h3>제약 검사</h3><ul>{(concept.constraint_check ?? []).map((check,index) => <li key={index}>{check.verdict === 'ok' ? '✓ 충족' : check.verdict === 'violates' ? '✕ 위반' : '⚠ 검토'} · {check.constraint} · {check.reason}</li>)}</ul>
 </section>;
}
export function InsightScreen({sid,version,readonly = false,initialConfirmed = []}: {sid: string; version?: string; readonly?: boolean; initialConfirmed?: string[]}) {
 const {refreshSessionAfterStage} = useVersion();
 const [data,setData] = useState<InsightResponse | null>(null);
 const [confirmed,setConfirmed] = useState(initialConfirmed);
 const [selected,setSelected] = useState(''); const [target,setTarget] = useState<InsightTarget>('insights');
 const [preview,setPreview] = useState<number | null>(null); const [busy,setBusy] = useState(false); const lock = useRef(false);
 const [error,setError] = useState(''); const [retry,setRetry] = useState(0);
 const [pending,setPending] = useState<{runId:string; mode:'derive'|'concept'; target?:string} | null>(null);
 const worker = data?.worker;
 const running = worker?.status === 'running';
 const stopped = worker?.status === 'failed' || worker?.status === 'interrupted';
 const failureVisible = stopped && (!pending || worker.runId === pending.runId || (!worker.runId && worker.mode === pending.mode && worker.target === (pending.target ?? null)));
 const disabled = readonly || busy || (!!pending && !failureVisible) || running;
 useStageCompletionRefresh(data?.insights.revision ? `insight:${data.insights.revision}` : null);
 useEffect(() => {
  let active = true;
  api.getInsights(sid,version).then(result => {if(active) {setData(result);setConfirmed(result.confirmed ?? []);setSelected(result.bars?.targets[0] ?? result.insights.items.find(item => record(item).default_target)?.id ?? '');setError('');}}).catch(cause => {if(active) setError(displayError(cause));});
  return () => {active = false;};
 },[sid,version,retry]);
 useEffect(() => {
  if (!pending && !running) return;
  let active = true; let count = 0;
  const timer = setInterval(async () => {
   try {
    const result = await api.getInsights(sid,version);
    if (!active) return;
    setData(result);setConfirmed(result.confirmed ?? []);
    if (result.worker && result.worker.status !== 'running' && (!pending || result.worker.runId === pending.runId || (!result.worker.runId && result.worker.mode === pending.mode && result.worker.target === (pending.target ?? null)))) {setPending(null);return;}
    if (++count >= 120) {setPending(null);setError('처리 상태를 확인하지 못했습니다. 다시 불러오세요.');}
   } catch(cause) {if(active) {setPending(null);setError(displayError(cause));}}
  },3000);
  return () => {active = false;clearInterval(timer);};
 },[sid,version,pending,running]);
 const actions = createInsightActions(sid,version,api,result => {setData(result);setConfirmed(result.confirmed ?? []);setPreview(null);},setConfirmed);
 async function mutate(action: () => Promise<unknown>) {
  if(disabled || lock.current) return;
  lock.current = true;setBusy(true);setError('');
  try {await action();} catch(cause) {setError(displayError(cause));} finally {lock.current = false;setBusy(false);}
 }
 const revisions = target === 'insights' ? data?.insights : data?.concepts;
 const history = revisions?.history ?? [];
 const viewed = preview === null ? null : history.find(row => row.revision === preview);
 const insightItems = target === 'insights' && Array.isArray(viewed?.items) ? viewed.items as InsightItem[] : data?.insights.items ?? [];
 const concepts = target !== 'insights' && Array.isArray(viewed?.items) ? viewed.items as InsightConcept[] : data?.concepts.items ?? [];
 const concept = concepts.find(row => (row.insight_id ?? row.id) === selected);
 const currentItems = data?.insights.items ?? [];
 const historicalInsights = preview !== null && target === 'insights';
 const metricItems = historicalInsights ? insightItems : currentItems;
 const rawBars = historicalInsights ? null : data?.bars?.bars;
 const bars = Array.isArray(rawBars) ? rawBars.map(value => {const row = record(value); return {id:text(row.id),label:currentItems.find(item => item.id === row.id)?.title ?? text(row.id),value:number(row.odi ?? row.value) ?? 0};}) : metricItems.flatMap(item => {const value = number(record(item).odi);return value === null ? [] : [{id:item.id,label:item.title,value}];});
 const mean = (historicalInsights ? null : data?.bars?.mean) ?? number(record(metricItems[0]).opportunity_mean);
 return <div className="space-y-5">
  <header className="ds-actions"><h1 className="ds-t-title">인사이트</h1>{!currentItems.length && <Button variant="primary" disabled={disabled} onClick={() => void mutate(async () => {const run = await api.startInsight(sid,{mode:'derive'},version);setPending({runId:run.runId,mode:'derive'});})}>인사이트 도출</Button>}</header>
  {readonly && <p>읽기 전용</p>}{((pending && !failureVisible) || running) && <p role="status">처리 중…</p>}
  {error && <div role="alert">{error}<Button onClick={() => setRetry(value => value+1)}>다시 불러오기</Button></div>}
  {!data && !error && <p role="status">불러오는 중…</p>}
  {failureVisible && <div role="alert"><p>{worker.mode === 'concept' ? '컨셉을 만들지 못했습니다. 다시 시도하세요.' : '인사이트를 만들지 못했습니다. 다시 시도하세요.'}</p>{worker.reason && <p>{worker.reason}</p>}<Button disabled={disabled} onClick={() => void mutate(async () => {const mode = worker.mode ?? 'derive';const run = await api.startInsight(sid,{mode,...(worker.target ? {target:worker.target} : {})},version);setPending({runId:run.runId,mode,target:worker.target ?? undefined});})}>{worker.status === 'interrupted' ? '이어서 진행' : '다시 시도'}</Button></div>}
  {data && !currentItems.length && !pending && !running && !stopped && <p role="status">페르소나를 바탕으로 인사이트를 도출하세요.</p>}
  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
   <main className="lg:col-span-2 min-w-0 space-y-5">
    {preview !== null && <p role="status">판 {preview} 보기 <Button onClick={() => setPreview(null)}>현재 판으로</Button></p>}
    {insightItems.map(item => <article key={item.id} className="ds-card space-y-3" aria-label={item.title}>
     <Button disabled={busy} aria-pressed={selected === item.id} onClick={() => {setSelected(item.id);setPreview(null);if(target !== 'insights') setTarget(`concept:${item.id}`);}}>{item.title}</Button>
     <p>{item.pain_point}</p><div className="flex flex-wrap gap-2">{item.context_ids.map(id => <span className="ds-badge" key={id}>{id}</span>)}</div>
     <span className="ds-badge">{item.known_ki_id ? `Known Insight #${item.known_ki_id}와 같은 내용` : '새 발견'}</span>
     <Radar values={radarValues(record(item).radar ?? data?.radar?.[item.id])}/>
     <label><input type="checkbox" checked={confirmed.includes(item.id)} disabled={disabled || preview !== null} onChange={event => {const ids = event.target.checked ? [...confirmed,item.id] : confirmed.filter(id => id !== item.id);void mutate(async () => {await actions.confirm(ids);await refreshSessionAfterStage();});}}/> 확정</label>
    </article>)}
    <OpportunityBars bars={bars} mean={mean}/>
    {selected && <section className="space-y-3"><h2>선택 인사이트 · {currentItems.find(item => item.id === selected)?.title}</h2>{concept && !concept.outdated ? <ConceptDetail concept={concept}/> : <>{concept?.outdated && <p>인사이트가 바뀌어 컨셉을 다시 만들어야 합니다.</p>}<Button disabled={disabled || preview !== null} onClick={() => void mutate(async () => {const run = await api.createInsightConcept(sid,selected,version);setPending({runId:run.runId,mode:'concept',target:selected});})}>{concept?.outdated ? '컨셉 다시 만들기' : '선택 컨셉 만들기'}</Button></>}</section>}
   </main>
   <aside className="min-w-0 space-y-5" aria-label="인사이트 수정">
    <label>채팅 대상 <select className="ds-inp" value={target} disabled={busy || !!pending || running} onChange={event => {setTarget(event.target.value as InsightTarget);setPreview(null);}}><option value="insights">인사이트 목록</option><option value={`concept:${selected}`} disabled={!concept || concept.outdated}>선택 컨셉</option></select></label>
    <div style={{height:420}}><ChatPanel key={target} initialMessage="수정할 내용을 알려 주세요." readonly={disabled} onSend={async message => {if(disabled || lock.current) return '처리 중입니다.';let reply = '';await mutate(async () => {reply = await actions.chat(target,message);});return reply;}}/></div>
    <RevisionList revisions={history.flatMap(row => typeof row.revision === 'number' ? [{revision:row.revision,message:text(row.message),by:text(row.by),createdAt:text(row.at ?? row.createdAt)}] : [])} currentRevision={revisions?.revision ?? 0} busy={disabled} onView={setPreview} onRevert={revision => void mutate(() => actions.revert(target,revision))}/>
   </aside>
  </div>
 </div>;
}
