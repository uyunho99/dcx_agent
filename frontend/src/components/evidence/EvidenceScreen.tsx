'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Badge, Banner, Button, Card, ProgressBar, Skeleton, Tabs } from '../ds';
import { StaleBanner } from '../versions/StageVersion';
import { useVersion } from '../versions/VersionProvider';
import { useStageCompletionRefresh } from '../versions/useStageCompletionRefresh';
import * as api from '@/lib/api/evidence';
import { addKnownInsight } from '@/lib/api/known';
import { getSegmentContexts, getSegmentPersonas, getSegmentStatus } from '@/lib/api/segment';
import { displayError } from '@/lib/api/errors';
import type { EvidenceContextResponse, EvidenceItemView, EvidencePersonaResponse, EvidenceStatus, EvidenceTab, SegmentPersona } from '@/lib/types';
import { canBuildPersona, excludedMessage, rowBadge } from './evidenceView';
import { EvidenceCard } from './EvidenceCard';
import { ContextList } from './ContextList';
import { QueryPanel } from './QueryPanel';

const prerequisites = '6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요.';
const staleCopy = '6단계가 다시 나뉘어 이 근거는 이전 결과 기준입니다. 다시 실행하세요.';
export function evidenceActions(sid:string, version:string | undefined, run:string, transport: Pick<typeof api, 'refreshEvidenceNew' | 'startEvidence' | 'skipEvidenceContext'> & {addKnownInsight:typeof addKnownInsight} = {...api,addKnownInsight}) {
  return {
    add:(docId:string) => transport.addKnownInsight(sid,{type:'doc',doc_id:docId},version),
    refresh:(id:string) => transport.refreshEvidenceNew(sid,id,{run},version),
    retry:(id:string) => transport.startEvidence(sid,{contexts:[id]},version),
    skip:(id:string) => transport.skipEvidenceContext(sid,id,{run},version),
  };
}
type Persona = Pick<SegmentPersona,'id'|'clusterId'|'name'|'flags'>;
type ViewProps = {
  sid:string;version?:string;status:EvidenceStatus | null;personas:Persona[];selectedPersona:string;selectedContext:string;
  tab:EvidenceTab;detail:EvidenceContextResponse | null;personaEvidence:EvidencePersonaResponse | null;
  ready:boolean;readonly:boolean;busy:boolean;error:string;flags?:Record<string,string[]>;added?:string[];
  onPersona:(id:string)=>void;onContext:(id:string)=>void;onTab:(tab:EvidenceTab)=>void;
  onStart:()=>void;onRetry:(id:string)=>void;onSkip:(id:string)=>void;onRefresh:(id:string)=>void;
  onAdded:(docId:string)=>void;onNext:()=>void;onReload?:()=>void;
};
export function EvidenceScreenView(p:ViewProps) {
  const {status,detail} = p;
  const rows = status?.contexts ?? [];
  const completedCount = rows.filter(row => row.status === 'done' || row.status === 'skipped').length;
  const selected = rows.find(row => row.id === p.selectedContext);
  const disabled = p.readonly || p.busy || status?.status === 'stale';
  const before = !status || ['none','stale'].includes(status.status);
  const done = !!status && status.status === 'done' && canBuildPersona(status);
  const cards = (items:EvidenceItemView[]) => items.map(item => <EvidenceCard key={item.docId} item={item} readonly={disabled} added={p.added?.includes(item.docId)} onAdd={p.onAdded}/>);
  const content = detail && detail.tab === p.tab ? <div className="space-y-3">
    {p.tab === 'new' && detail.excludedKnown > 0 && <Banner actions={<Button onClick={() => p.onTab('all')}>전체 탭에서 보기</Button>}>{excludedMessage(detail.excludedKnown)}</Banner>}
    {detail.items.length ? cards(detail.items) : <p>{p.tab === 'new' && (selected?.counts.all ?? 0) > 0 ? 'Known Insight를 빼니 남는 원문이 없습니다. 전체 탭에서 보세요.' : '이 Context에서 근거로 쓸 원문을 찾지 못했습니다.'}</p>}
  </div> : <div role="status" aria-label="근거 불러오는 중"><Skeleton height={120}/></div>;
  return <div className="min-w-0 space-y-5 break-words">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="ds-eyebrow">7단계 · 근거 탐색</p><h1 className="ds-t-screen">아직 모르는 근거를 찾습니다</h1><p className="ds-t-body">Context마다 소비자 말투의 가설 문장 8개로 그 Context 안에서만 찾고, 10건을 고릅니다.</p></div>
      {before ? <Button variant="primary" disabled={!status || !p.ready || p.readonly || p.busy} onClick={p.onStart}>근거 탐색 실행</Button> : <Button variant="primary" disabled={!done || p.readonly || p.busy} title={!done ? '모든 Context가 끝나야 합니다' : undefined} onClick={p.onNext}>페르소나 만들기</Button>}
    </header>
    {!p.ready && <Banner>{prerequisites}</Banner>}
    {status?.status === 'stale' && <Banner tone="warning">{staleCopy}</Banner>}
    {p.error && <Banner tone="danger" actions={<Button onClick={p.onReload}>새로고침</Button>}>{p.error}</Banner>}
    {status?.reason && <Banner tone="warning">{status.reason}</Banner>}
    {status && ['interrupted','failed'].includes(status.status) && <Banner actions={<Button disabled={disabled || !p.ready} onClick={p.onStart}>이어서 진행</Button>}>근거 탐색이 중단되었습니다.</Banner>}
    {status?.status === 'running' && <div role="status"><p>Context {completedCount}/{rows.length} · 태깅 호출 {Number(status.stage7?.tag_calls ?? 0)}회</p><ProgressBar label="근거 탐색 진행" value={rows.length ? completedCount : undefined} max={rows.length}/><p>끝난 Context부터 열어 볼 수 있습니다.</p></div>}
    <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <aside className="min-w-0 space-y-4"><Card size="sm"><nav aria-label="Persona 목록" className="space-y-3"><h2 className="ds-t-label">Persona</h2>
        {Array.from(new Set(p.personas.map(row => row.clusterId))).map(cluster => <div key={cluster} className="space-y-2"><h3>{cluster}</h3>{p.personas.filter(row => row.clusterId === cluster).map(persona => {
          const owned = rows.filter(row => row.personaId === persona.id);
          const state = owned.some(r => r.status === 'failed') ? 'failed' : owned.some(r => r.status === 'running') ? 'running' : owned.length && owned.every(r => r.status === 'done' || r.status === 'skipped') ? 'done' : 'queued';
          return <Button className="w-full whitespace-normal text-left" key={persona.id} aria-current={p.selectedPersona === persona.id ? 'true' : undefined} onClick={() => p.onPersona(persona.id)}>{persona.name || persona.id} <Badge>{rowBadge(state)}</Badge>{persona.flags.includes('future') && <Badge tone="warning">FUTURE</Badge>}</Button>;
        })}</div>)}
      </nav></Card><ContextList rows={rows.filter(row => row.personaId === p.selectedPersona)} selected={p.selectedContext} disabled={disabled} flags={p.flags} onSelect={p.onContext} onRetry={p.onRetry} onSkip={p.onSkip} onRefresh={p.onRefresh}/></aside>
      <section className="min-w-0 space-y-4" aria-label="Context 근거">{selected?.status === 'done' ? <><h2 className="ds-t-card">{selected.id} · {selected.name}</h2>
        <Tabs label="근거 탭" value={p.tab} onChange={value => p.onTab(value as EvidenceTab)} items={[{value:'all',label:'전체',count:selected.counts.all ?? 0,content:p.tab === 'all' ? content : null},{value:'new',label:'새 발견',count:selected.counts.new ?? 0,content:p.tab === 'new' ? content : null}]}/>
        {detail && <><QueryPanel queries={detail.queries} failed={detail.queryFailed}/>{detail.undifferentiated.length > 0 && <Badge tone="warning">⚠ 미분화 후보 · 원문 {detail.undifferentiated.length}건</Badge>}
          <details className="ds-card space-y-3"><summary>반례 {detail.counter.length} · 희소 {detail.rare.length}</summary>{cards(detail.counter)}{cards(detail.rare)}</details></>}
      </> : <Card>완료된 Context를 선택하세요.</Card>}
      <details className="ds-card space-y-3"><summary>Persona 근거 · Desire 검증 · 쓰는 제품 · 수단</summary>{p.personaEvidence ? <>{cards(p.personaEvidence.desireSupport)}{p.personaEvidence.artifacts.map((artifact,i) => <p key={i}>{Object.values(artifact).filter(v => typeof v === 'string').join(' · ')}</p>)}</> : <p>완료된 근거가 없습니다.</p>}</details>
      </section>
    </div>
  </div>;
}

export function EvidenceScreen({sid,version,readonly = false}: {sid:string;version?:string;readonly?:boolean}) {
  const view = useVersion();
  const router = useRouter();
  const [status,setStatus] = useState<EvidenceStatus | null>(null);
  const [personas,setPersonas] = useState<Persona[]>([]);
  const [flags,setFlags] = useState<Record<string,string[]>>({});
  const [ready,setReady] = useState(false);
  const [selectedPersona,setPersona] = useState('');
  const [selectedContext,setContext] = useState('');
  const [tab,setTab] = useState<EvidenceTab>('new');
  const [detail,setDetail] = useState<EvidenceContextResponse | null>(null);
  const [personaEvidence,setPersonaEvidence] = useState<EvidencePersonaResponse | null>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [added,setAdded] = useState<string[]>([]);
  const [revision,setRevision] = useState(0);
  const active = useRef(true);
  const generation = useRef<string | null>(null);
  const request = useRef(0);
  const lock = useRef(false);
  const blocked = readonly || !!view.conflict;
  useEffect(() => {active.current = true; return () => {active.current = false;};}, []);
  const loadStatus = useCallback(async () => {
    const token = ++request.current;
    const result = await api.getEvidenceStatus(sid,version);
    if (!active.current || token !== request.current) return;
    if (result.run !== generation.current) {
      generation.current = result.run; setDetail(null); setPersonaEvidence(null); setAdded([]); setContext('');
    }
    setStatus(result);
  },[sid,version]);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {if(!lock.current) await loadStatus();} catch(e) {if(!cancelled) setError(displayError(e));}
      if(!cancelled && !readonly) timer = setTimeout(poll,3000);
    }
    void poll();
    return () => {cancelled = true; clearTimeout(timer);};
  },[loadStatus,readonly]);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [segment, people, contexts] = await Promise.all([getSegmentStatus(sid,version),getSegmentPersonas(sid,undefined,version),getSegmentContexts(sid,undefined,version)]);
      if(cancelled) return;
      const [done,total] = segment.confirm.contexts.split('/').map(Number);
      setReady(segment.status === 'done' && total > 0 && done === total && people.run === segment.run && contexts.run === segment.run);
      setPersonas(people.personas);
      setFlags(Object.fromEntries(contexts.contexts.map(c => [c.id,c.flags])));
      setPersona(previous => people.personas.some(p => p.id === previous) ? previous : people.personas[0]?.id ?? '');
    }
    void load().catch(e => {if(!cancelled) setError(displayError(e));});
    return () => {cancelled = true;};
  },[sid,version,revision,status?.status]);
  const chosen = status?.contexts.find(c => c.id === selectedContext && c.personaId === selectedPersona && c.status === 'done')
    ?? status?.contexts.find(c => c.personaId === selectedPersona && c.status === 'done');
  const chosenId = chosen?.id;
  const personaCompleted = status?.contexts.filter(c => c.personaId === selectedPersona && c.status === 'done').map(c => c.id).join('|');
  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    if(chosenId && status?.status !== 'stale') void api.getEvidenceContext(sid,chosenId,tab,version).then(result => {if(!cancelled) setDetail(result);}).catch(e => {if(!cancelled) setError(displayError(e));});
    return () => {cancelled = true;};
  },[sid,version,chosenId,tab,status?.run,status?.status,revision]);
  useEffect(() => {
    let cancelled = false;
    setPersonaEvidence(null);
    if(selectedPersona && status?.run && status.status !== 'stale') void api.getEvidencePersona(sid,selectedPersona,version).then(result => {if(!cancelled) setPersonaEvidence(result);}).catch(e => {if(!cancelled) setError(displayError(e));});
    return () => {cancelled = true;};
  },[sid,version,selectedPersona,personaCompleted,status?.run,status?.status,revision]);
  useStageCompletionRefresh(status?.status === 'done' ? status.run : null);
  async function mutate(work:()=>Promise<unknown>) {
    if(blocked || lock.current) return;
    lock.current = true; request.current++; setBusy(true); setError('');
    try {await work(); if(active.current) {await loadStatus();setRevision(n => n+1);}}
    catch(e) {if(active.current) {setError(displayError(e));await loadStatus().catch(() => {});}}
    finally {lock.current = false; if(active.current) setBusy(false);}
  }
  const actions = evidenceActions(sid,version,status?.run ?? '');
  async function add(docId:string) {
    if(!status?.run || status.status === 'stale') return;
    await mutate(async () => {
      await actions.add(docId);
      if(!active.current) return;
      setAdded(previous => [...previous,docId]);
      setStatus(previous => previous ? {...previous,contexts:previous.contexts.map(row => row.status === 'done' ? {...row,knownChanged:true} : row)} : previous);
      // Keep every completed row marked until the user requests recalculation (D-223).
    });
  }
  function start() {if(!ready || status?.status === 'running') return; void mutate(() => api.startEvidence(sid,status?.status === 'stale' ? {fresh:true} : {},version));}
  return <>{readonly && <Banner>{version} · 읽기 전용</Banner>}<StaleBanner stage="stage7" session={view.session}/><EvidenceScreenView sid={sid} version={version} status={status} personas={personas} flags={flags} selectedPersona={selectedPersona} selectedContext={chosen?.id ?? ''} tab={tab} detail={detail} personaEvidence={personaEvidence} ready={ready} readonly={blocked} busy={busy} error={error} added={added}
    onPersona={id => {setDetail(null);setPersonaEvidence(null);setPersona(id);setContext('');setTab('new');}} onContext={id => {setDetail(null);setContext(id);setTab('new');}} onTab={next => {setDetail(null);setTab(next);}} onStart={start}
    onRetry={id => {if(status?.run && status.status !== 'stale') void mutate(() => actions.retry(id));}} onSkip={id => {if(status?.run && status.status !== 'stale') void mutate(() => actions.skip(id));}}
    onRefresh={id => {if(status?.run && status.status !== 'stale') void mutate(async () => {await actions.refresh(id);});}} onAdded={docId => void add(docId)}
    onNext={() => {if(status?.status === 'done' && canBuildPersona(status) && !blocked) router.push('/pipeline/personas');}}
    onReload={() => {setError('');setRevision(n => n+1);void loadStatus().catch(e => setError(displayError(e)));}}/></>;
}
