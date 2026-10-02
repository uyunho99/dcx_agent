'use client';
import { useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import * as api from '@/lib/api/persona';
import { getSegmentPersonas } from '@/lib/api/segment';
import { addKnownInsight } from '@/lib/api/known';
import { ApiError, displayError } from '@/lib/api/errors';
import { usePolling } from '@/lib/usePolling';
import { useStageCompletionRefresh } from '../versions/useStageCompletionRefresh';
import { Button, Badge } from '../ds';
import { GradeMark } from './GradeMark';
import { CCMTable, ccmRows, type CCMContext } from './CCMTable';
import { OpportunityMap } from './OpportunityMap';
import { ContextTable } from './ContextTable';
import { zoneName, formatMetric, formatCount, displayValue } from './personaView';
import { HierarchyTree, type HierarchyNode } from './HierarchyTree';
import type { PersonaCardsResponse, PersonaGrade, PersonaMap, PersonaStatus, PersonaTree, SegmentPersona } from '@/lib/types';

const missingCopy = '근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다.';
const quoteWarning = '인용 문장을 원문에서 찾지 못해 추론으로 낮췄습니다.';
const tabs = ['8-A CCM', '8-B 수렴', '8-C 속성', '8-D 처방', '구조 트리'] as const;
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const rows = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.map(record) : [];
const label = (value: unknown): string => displayValue(value, '근거 부족');
const needsEvidence = (cause: unknown) => cause instanceof ApiError && ['evidence_required','not_ready'].includes(cause.kind ?? '');
const grade = (value: unknown): PersonaGrade | null => value === 'observed' || value === 'inferred' || value === 'speculated' ? value : null;
const running = (status?: string) => ['queued', 'running', 'paused'].includes(status ?? '');
const statusLabel = (status?: string) => ({done:'완료',failed:'실패',running:'진행 중',queued:'대기',pending:'대기',stale:'갱신 필요',interrupted:'중단',paused:'일시 정지'}[status ?? ''] ?? '대기');
function hierarchy(value: unknown): HierarchyNode {
  const node = record(value);
  return {id:String(node.id ?? 'product'),name:String(node.name ?? '제품'),doc_count:Number(node.doc_count ?? node.size ?? 0),children:rows(node.children).map(hierarchy)};
}
type Snapshot = {status: PersonaStatus; cards: PersonaCardsResponse; map: PersonaMap | null; tree: PersonaTree | null; identities: SegmentPersona[]; missing?: boolean; error?: string};
type Props = {sid: string; version?: string; readonly?: boolean};

export function PersonaScreen({sid, version, readonly = false}: Props) {
  const router = useRouter();
  const [view, setView] = useState<'map' | 'card'>('map');
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState<typeof tabs[number]>('8-A CCM');
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [missing, setMissing] = useState(false);
  const [notice, setNotice] = useState('');
  const lock = useRef(false);
  const cache = useRef<Snapshot | null>(null);
  const cacheKey = useRef('');
  const fetcher = useCallback(async (): Promise<Snapshot> => {
    try {
      const status = await api.getPersonaStatus(sid, version);
      setMissing(false);
      setError('');
      setPending(false);
      const key = JSON.stringify(status);
      if (cache.current && cacheKey.current === key) return cache.current;
      const results = await Promise.allSettled([
        api.getPersonaCards(sid, version), api.getPersonaMap(sid, version),
        api.getPersonaTree(sid, version), getSegmentPersonas(sid, undefined, version),
      ]);
      const [cards, map, tree, identities] = results;
      const failures = results.filter(result => result.status === 'rejected');
      const missingEvidence = cards.status === 'rejected' && needsEvidence(cards.reason) && (cards.reason.kind === 'evidence_required' || ['none','idle'].includes(status.status));
      const result: Snapshot = {status,
        cards:cards.status === 'fulfilled' ? cards.value : {run:status.run,personas:{}},
        map:map.status === 'fulfilled' ? map.value : null,
        tree:tree.status === 'fulfilled' ? tree.value : null,
        identities:identities.status === 'fulfilled' ? identities.value.personas : [], missing:missingEvidence,
        error: status.status === 'done' && failures.length ? '일부 결과를 불러오지 못했습니다. 다시 불러오세요.' : undefined,
      };
      // Only cache complete results; transient reads can recover on the next poll.
      if (!failures.length) {cacheKey.current = key; cache.current = result;}
      setError('');
      return result;
    } catch (cause) {setPending(false);const message = displayError(cause);setError(message);if(needsEvidence(cause) || message.includes(missingCopy)) setMissing(true);throw cause;}
  }, [sid, version]);
  const {data, refresh} = usePolling({fetcher,interval:3000,enabled:true});
  const status = data?.status;
  useStageCompletionRefresh(status?.status === 'done' ? `persona:${version ?? ''}:${status.run}` : null);
  const blocked = readonly || busy || pending || running(status?.status);
  const complete = status?.status === 'done';
  const cards = data?.cards.personas ?? {};
  const ids = [...new Set([...(data?.identities ?? []).map(p => p.id),...Object.keys(cards),...(status?.personas ?? []).map(p => p.id)])];
  const identity = (id: string) => data?.identities.find(p => p.id === id);
  const body = (id: string) => record(cards[id]?.card);
  const name = (id: string) => identity(id)?.name ?? String(body(id).persona_name ?? id);
  const cluster = (id: string) => identity(id)?.clusterId ?? String(body(id).cluster_id ?? data?.map?.points.find(p => p.persona_id === id)?.cluster_id ?? 'Persona');
  const chosen = ids.includes(selected) ? selected : ids[0];
  const current = cards[chosen];
  const card = body(chosen);
  const contexts = rows(card.contexts);
  const metrics = record(card.metrics);
  const state = status?.personas.find(p => p.id === chosen)?.status ?? current?.status;
  const openCard = (id: string, contextId?: string) => {setSelected(id);setHighlighted(contextId ?? null);setView('card');setTab('8-A CCM');};
  async function mutate(action: () => Promise<unknown>, waitForPoll = false) {
    if (blocked || lock.current) return;
    lock.current = true;setBusy(true);setError('');setNotice('');
    try {await action();cacheKey.current = '';setPending(waitForPoll);refresh();}
    catch (cause) {const message = displayError(cause);setError(message);if(needsEvidence(cause) || message.includes(missingCopy)) setMissing(true);}
    finally {lock.current = false;setBusy(false);}
  }
  const evidence = (contextId: string | null, field: string) => {
    const traces = rows(current?.trace ?? card.trace).filter(row => row.context_id === contextId && row.field === field);
    return traces.length ? <ul className="space-y-3">{traces.map((trace, index) => {
      const ref = record(trace.evidence), quote = record(ref.quote);
      return <li key={`${trace.evidence_id}:${index}`}><Badge>{label(ref.source)}</Badge> <span>{label(trace.evidence_id)} · {label(quote.field)} {quote.idx == null ? '' : String(quote.idx)} · {label(quote.start)}–{label(quote.end)}</span><blockquote title={quote.verified === false ? quoteWarning : undefined}><mark>{label(quote.text)}</mark></blockquote>{quote.verified === false && <span title={quoteWarning} aria-label={quoteWarning}>▲ 추론 · 인용 미확인</span>}<Button size="sm" disabled={blocked || typeof ref.doc_id !== 'string'} onClick={() => mutate(async () => {await addKnownInsight(sid,{type:'doc',doc_id:String(ref.doc_id)},version);setNotice('Known Insight에 추가했습니다.');})}>Known Insight에 추가</Button></li>;
    })}</ul> : <p>근거가 없습니다.</p>;
  };
  const ccm: CCMContext[] = contexts.map(context => {
    const id = String(context.context_id); const point = data?.map?.points.find(p => p.context_id === id);
    const grades = record(record(current?.grades ?? card.grades)[id]);
    return {id,name:String(context.context_name ?? id),counter:point?.counter ?? false,cells:Object.fromEntries(ccmRows.map(([field]) => {
      const value = field === 'artifact' ? rows(card.artifacts).map(item => `${label(item.name)} (${formatCount(Number(item.mention_count))}건)`).join(' · ') || null : field === 'satisfaction' ? record(context.metrics).satisfaction : field === 'opportunity' ? point ? `${zoneName(point.zone)} · ${formatMetric(point.odi)}` : record(context.metrics).odi : context[field];
      return [field,{text:label(value),...(['state','emotion','barrier'].includes(field) ? {grade:grade(grades[field])} : {}),evidence:evidence(id,field)}];
    }))};
  });
  const prescription = current?.prescription;
  const constraints = prescription?.constraint ?? current?.constraint ?? [];
  const contextRows = data?.map?.points.map(point => ({...point,persona_name:name(point.persona_id),name:String(rows(body(point.persona_id).contexts).find(c => c.context_id === point.context_id)?.context_name ?? point.context_id)})) ?? [];
  const highlightedRow = contextRows.find(row => row.context_id === highlighted);
  if (missing || data?.missing) return <section className="ds-card space-y-4"><p>{missingCopy}</p><Button onClick={() => router.push('/pipeline/evidence')}>근거 탐색으로</Button></section>;
  return <section className="space-y-5 min-w-0">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="ds-eyebrow">8단계 · 페르소나</p><h1 className="ds-t-screen">{view === 'map' ? '세션 전체에서 어느 Context가 기회인가' : chosen ? name(chosen) : 'Persona 카드'}</h1>{readonly && <p>{version} · 읽기 전용</p>}</div><Button variant="primary" disabled={blocked || !status} onClick={() => complete ? router.push('/pipeline/insights') : mutate(() => api.startPersona(sid,status?.status === 'stale' ? {fresh:true} : {},version),true)}>{complete ? '인사이트 도출' : '페르소나 만들기'}</Button></header>
    {(error || data?.error) && <div role="alert">{error || data?.error} <Button onClick={() => {cacheKey.current='';refresh();}}>다시 불러오기</Button></div>}
    {notice && <p role="status">{notice}</p>}
    {(pending || running(status?.status)) && <p role="status">페르소나를 만들고 있습니다. {Math.round((status?.progress ?? 0) * 100)}% · 화면을 닫아도 계속됩니다.</p>}
    {status?.status === 'stale' && <p role="status">근거 또는 확정값이 바뀌었습니다. 페르소나를 다시 만들어 주세요.</p>}
    <div className="grid gap-5 md:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label="Persona 목록" className="ds-card space-y-4 min-w-0">{[...new Set(ids.map(cluster))].map(group => <div key={group}><h2 className="ds-t-label">{group}</h2>{ids.filter(id => cluster(id) === group).map(id => <Button key={id} className="w-full h-auto whitespace-normal text-left my-1" aria-current={chosen === id ? 'true' : undefined} onClick={() => openCard(id)}>{name(id)} <Badge>{statusLabel(status?.personas.find(p => p.id === id)?.status ?? cards[id]?.status)}</Badge>{cards[id]?.scope?.verdict === 'outside' && <Badge>FUTURE</Badge>}</Button>)}</div>)}</nav>
      <div className="min-w-0 space-y-4"><div role="group" aria-label="보기" className="flex gap-2"><Button aria-pressed={view === 'map'} onClick={() => setView('map')}>전체 맵</Button><Button aria-pressed={view === 'card'} onClick={() => setView('card')}>Persona 카드</Button></div>
      {!data ? <p role="status">페르소나 정보를 불러오는 중…</p> : view === 'map' ? data.map ? <>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(160px,1fr)]"><OpportunityMap map={data.map} highlightedId={highlighted} selectedPersonaId={selected || null} onHighlight={setHighlighted} onOpenCard={openCard}/><aside className="ds-card" aria-label="선택 Context 상세">{highlightedRow ? <><h2>{highlightedRow.name}</h2><p>{highlightedRow.persona_name} · {zoneName(highlightedRow.zone)} · 기회 {formatMetric(highlightedRow.odi)}</p><Button onClick={() => openCard(highlightedRow.persona_id,highlightedRow.context_id)}>카드 열기</Button></> : <p>점을 가리키거나 아래 표에서 Context를 고르세요.</p>}</aside></div>
        <div className="overflow-x-auto"><ContextTable rows={contextRows} highlightedId={highlighted} onHighlight={setHighlighted} onOpenCard={openCard}/></div>
      </> : <p>페르소나를 만들면 전체 맵과 Context를 확인할 수 있습니다.</p> : !chosen ? <p>아직 페르소나 카드가 없습니다.</p> : <>
        <header className="ds-card space-y-2"><h2 className="ds-t-card">{name(chosen)} {current?.scope?.verdict === 'outside' && <Badge title={current.scope.reason}>FUTURE</Badge>}</h2><p>{`근거 ${formatCount(Number(metrics.doc_count ?? identity(chosen)?.docs))}건 · 작성자 ${formatCount(Number(metrics.author_count ?? identity(chosen)?.authors))}명 · Context ${formatCount(contexts.length)}개`}</p><p>Desire · {label(identity(chosen)?.desire ?? card.desire)}</p><p>Goal · {label(identity(chosen)?.goals ?? card.goal)}</p></header>
        {state === 'failed' ? <div role="alert"><p>이 페르소나 카드를 만들지 못했습니다.</p><Button disabled={blocked || !status?.run} onClick={() => mutate(() => api.retryPersonaCard(sid,chosen,{run:status!.run!},version),true)}>다시 만들기</Button></div> : !current?.card ? <p role="status">{statusLabel(state)} · 카드가 준비되면 표시됩니다.</p> : <>
          <div role="tablist" aria-label="Persona 상세" className="flex flex-wrap gap-2">{tabs.map(item => <Button key={item} role="tab" id={`persona-tab-${tabs.indexOf(item)}`} aria-controls="persona-panel" aria-selected={tab === item} onClick={() => setTab(item)}>{item}</Button>)}</div>
          <div role="tabpanel" id="persona-panel" aria-labelledby={`persona-tab-${tabs.indexOf(tab)}`} className="ds-card min-w-0 space-y-4">
            {tab === '8-A CCM' && <><p>각 칸은 개인이 아니라 그 Context에서 관측되는 담론입니다. 칸을 누르면 근거 원문이 펼쳐집니다.</p><CCMTable contexts={ccm}/></>}
            {tab === '8-B 수렴' && <><p role="note">의도 ≠ 행동</p><GradeMark grade="speculated"/><p>{label(record(card.intent).text)}</p><p>수렴 Context · {label(record(card.intent).basis_context_ids)}</p><p>유보 Context · {label(record(card.intent).reserved_context_ids)}</p></>}
            {tab === '8-C 속성' && <dl className="space-y-3">{[['usage_context','사용 맥락'],['jtbd','JTBD'],['journey','여정'],['sensitivity','민감도'],['values','가치관'],['decision_style','결정 방식']].map(([key,title]) => <div key={key}><dt>{title}</dt><dd>{['usage_context','jtbd'].includes(key) && <GradeMark grade={grade(record(card.summary)[key])}/>} {label(card[key])}{['usage_context','jtbd'].includes(key) && <details><summary>근거 원문</summary>{evidence(null,key)}</details>}</dd></div>)}</dl>}
            {tab === '8-D 처방' && <>{prescription ? <><h3>{prescription.blocked ? '처방 차단됨' : '처방'}</h3><p>{prescription.direction}</p><p>핵심 지표 · {displayValue(prescription.target_metric)}</p><p>기여 · {prescription.contribution}</p><p>여정 가설 · {prescription.journey_hypothesis}</p>{prescription.represcribed && <Badge>재처방</Badge>}</> : <p>처방이 없습니다.</p>}<ul>{constraints.map((constraint,index) => <li key={index}>{constraint.verdict === 'ok' ? '✓' : '⚠'} {constraint.constraint} · {constraint.reason}{prescription?.blocked && constraint.verdict === 'violates' && <p>{`사내 제약 '${constraint.constraint}'를 지키는 처방을 만들지 못했습니다.`}</p>}</li>)}</ul></>}
            {tab === '구조 트리' && (data.tree ? <HierarchyTree root={hierarchy(data.tree)}/> : <p>구조 트리가 준비되지 않았습니다.</p>)}
          </div>
        </>}
      </>}
      </div>
    </div>
  </section>;
}
