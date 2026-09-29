'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { VersionStage, StageVersionAction } from "@/components/versions/StageVersion";
import { useVersion } from "@/components/versions/VersionProvider";
import { versionPath, getVersionKeywords, getVersionRound } from "@/lib/api/versions";
import { useSessionStore } from '@/stores/useSessionStore';
import { Banner, Badge, BarList, Button, Card, ChoiceChips, Input, Popover, Select, Skeleton, Stepper, Tabs, type StepperItem } from '@/components/ds';
import { SaveBar } from '@/components/SaveBar';
import { KeywordGroup } from '@/components/keywords/KeywordGroup';
import { CoveragePanel } from '@/components/keywords/CoveragePanel';
import { axes, destinations, groupKey, groupLabel } from '@/components/keywords/taxonomy';
import { addKeyword, commitRound, getCoverage, KeywordApiError, postEvent, regenerateRound, startRound, suggestWords, type Axis, type Decision, type Destination, type Draft, type Keyword, type KeywordState, type Rejection } from '@/lib/api/keywords';
import { contextRequest, patchSession } from '@/lib/api/context';
import { filterKeywords, keywordFilters, type KeywordFilter } from '@/lib/logic/filterKeywords';
import { createActionQueue } from '@/lib/logic/actionQueue';
import { reviewKeywords } from '@/lib/logic/reviewKeywords';
import { roundUi } from '@/lib/logic/roundUi';
import { INTERNAL_TOOLS } from '@/lib/internalTools';
import '@/components/keywords/keywords.css';

const names = ['초기 발산', '인접 확장', '수렴 · 균형', '재발산', '최종 검토'];
const techniques = ['5W1H · JTBD', 'SCAMPER 대체·결합·응용', '분포 · 거절 · 커버리지', '역발상 · 제거 · 부정 공간', '크롤링으로 전달'];
const reasons: Record<string, string> = { interrupted: '서버 재시작', timeout: '응답 시간 초과', parse: '응답 형식 오류', parse_error: '응답 형식 오류', schema: '응답 형식 오류', validation: '응답 형식 오류', backend: '생성 도구 설정 오류', storage: '저장 공간 오류' };
export default function KeywordsPage() {
  const sid = useSessionStore(s => s.sid); const sd = useSessionStore(s => s.sd); const router = useRouter();
  if (!sid) return <Banner actions={<Button onClick={() => router.push('/pipeline/start')}>프로젝트 선택하기</Button>}>프로젝트를 먼저 선택하세요.</Banner>;
  if (sd?.schemaVersion !== 2) return <Banner tone="warning" actions={<Button onClick={() => router.push('/pipeline/preprocess')}>전처리 화면으로</Button>}>구버전 세션은 0~2단계를 편집할 수 없습니다. 3단계 이후 화면에서 결과를 확인하세요.</Banner>;
  return <VersionStage stage="stage1"><KeywordScreen key={sid} sid={sid} /></VersionStage>;
}
function KeywordScreen({ sid }: { sid: string }) {
  const { version, readonly } = useVersion();
  const [initialReadonly] = useState(readonly);
  const router = useRouter(); const [data, setData] = useState<KeywordState | null>(null); const [round, setRound] = useState(1);
  const [overrides, setOverrides] = useState<Record<string, Decision>>({}); const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false); const lock = useRef(false); const queue = useRef(createActionQueue()); const pendingActions = useRef(0); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [direction, setDirection] = useState(''); const [axis, setAxis] = useState(readonly ? 'all' : 'physical'); const [filter, setFilter] = useState<KeywordFilter>('판단 필요'); const [query, setQuery] = useState('');
  const [custom, setCustom] = useState<Destination[]>([]); const [customAxis, setCustomAxis] = useState(''); const [customName, setCustomName] = useState('');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({}); const [help, setHelp] = useState(false); const [elapsed, setElapsed] = useState(0);
  const [duplicate, setDuplicate] = useState<Keyword | null>(null);
  const current = data?.keywordRounds[String(round)]; const ui = roundUi({ round, status: current?.job.status, committed: current?.committed, gen: current?.gen, jobGen: current?.job.gen, dirty });
  const running = current?.job.status === 'running';
  const reportError = useCallback((e: unknown) => setError(e instanceof Error ? e.message : '요청에 실패했습니다. 다시 시도하세요.'), []);
  const reload = useCallback(async () => { const fresh = await getVersionKeywords(sid, version); setData(fresh); return fresh; }, [sid, version]);
  useEffect(() => {
    let cancelled = false;
    Promise.all([getVersionKeywords(sid, version), contextRequest<{ data: { drafts?: { keywords?: Record<string, Draft> } } }>(versionPath(`/session/${encodeURIComponent(sid)}`, version))]).then(([fresh, session]) => {
      if (cancelled) return;
      const n = Math.max(1, ...Object.keys(fresh.keywordRounds).map(Number)); const r = fresh.keywordRounds[String(n)];
      setData(fresh); setRound(n);
      const draft = session.data?.drafts?.keywords?.[`r${n}`];
      if (draft && draft.gen === (r?.gen ?? 0)) { if (!r?.committed) setOverrides(Object.fromEntries(draft.decisions.map(d => [d.id, d]))); setCustom(draft.groups ?? []); setNotice(initialReadonly ? '' : '임시 저장한 검토를 불러왔습니다. 저장하면 이 라운드를 확정합니다.'); }
      const kws = [...fresh.keywords, ...Object.values(fresh.keywordRounds).flatMap(r => r.keywords)];
      setFilter(!initialReadonly && filterKeywords(kws).length ? '판단 필요' : '전체');
    }).catch(e => { if (!cancelled) reportError(e); });
    return () => { cancelled = true; };
  }, [sid, version, initialReadonly, reportError]);
  useEffect(() => {
    if (!running || readonly) return;
    let cancelled = false; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const result = await getVersionRound(sid, round, version); if (cancelled) return;
        setData(old => old ? { ...old, keywordRounds: { ...old.keywordRounds, [round]: { ...old.keywordRounds[round], ...result, job: result } } } : old);
        if (result.status !== 'running') { const fresh = await reload(); setFilter(filterKeywords([...fresh.keywords, ...Object.values(fresh.keywordRounds).flatMap(r => r.keywords)]).length ? '판단 필요' : '전체'); return; }
      } catch (e) { if (!cancelled) reportError(e); }
      if (!cancelled) timer = setTimeout(poll, 3000);
    }
    void poll(); return () => { cancelled = true; clearTimeout(timer); };
  }, [running, round, sid, version, readonly, reload, reportError]);
  useEffect(() => {
    if (!running || !current?.job.startedAt) return;
    const started = Date.parse(current.job.startedAt);
    const timer = setInterval(() => setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000))), 1000);
    return () => clearInterval(timer);
  }, [running, current?.job.startedAt]);
  const all = reviewKeywords({ keywordRounds: data?.keywordRounds ?? {}, keywords: data?.keywords ?? [] }).map(k => overrides[k.id] ? { ...k, ...overrides[k.id] } : k);
  const groups = [...new Map([...destinations, ...custom, ...all.map(k => ({ axis: k.axis, sub: k.sub }))].map(g => [groupKey(g), g])).values()];
  const tabGroups = groups.filter(g => axis === 'all' || g.axis === axis);
  const tabKeywords = all.filter(k => axis === 'all' || k.axis === axis);
  const visible = filterKeywords(tabKeywords, filter, query);
  const isCollapsed = (g: Destination) => readonly ? false : collapsed[`${axis}:${groupKey(g)}`] ?? tabGroups.length >= 10;
  const decisions = (): Decision[] => (current?.keywords ?? []).map(k => overrides[k.id] ?? { id: k.id, status: k.status === 'rejected' ? 'rejected' : 'approved', reject: k.reject });
  async function action(fn: () => Promise<void>, waitForLock = false) {
    if (lock.current && !waitForLock) return;
    pendingActions.current += 1; lock.current = true; setBusy(true);
    await queue.current(async () => {
      setError(''); setNotice('');
      try { await fn(); } catch (e) { reportError(e); }
      finally { pendingActions.current -= 1; lock.current = pendingActions.current > 0; setBusy(lock.current); }
    });
  }
  async function saveDirection(targetRound = round) { if (direction.trim()) { const result = await postEvent(sid, { round: targetRound, type: 'direction', text: direction.trim() }); setData(d => d ? { ...d, feedback_md: result.feedback_md } : d); setDirection(''); } }
  async function generate(n: number, regenerate = false) { if ((dirty && current) || (regenerate && !ui.canRegenerate)) return; await action(async () => { await saveDirection(n); const job = await (regenerate ? regenerateRound(sid, n) : startRound(sid, n)); setOverrides({}); setDirty(false); setElapsed(0); setRound(n); setData(d => d ? { ...d, keywordRounds: { ...d.keywordRounds, [n]: { round: n, gen: job.gen, job, committed: false, keywords: [] } } } : d); await patchSession(sid, { step: `r${n}` }); useSessionStore.getState().setSession({ step: `r${n}` }); }); }
  async function review(k: Keyword, rejection: Rejection | null, to?: Destination) {
    let failed: unknown;
    await action(async () => { try {
      await postEvent(sid, { round, type: rejection ? 'reject' : 'unreject', kwId: k.id, tags: rejection?.tags, note: rejection?.note });
      setOverrides(o => ({ ...o, [k.id]: { id: k.id, status: rejection ? 'rejected' : 'approved', reject: rejection } })); setDirty(!current?.committed); if (!rejection && filter === '거절됨') { setFilter('전체'); }
      if (to) { await postEvent(sid, { round, type: 'move', kwId: k.id, to }); reveal(to); }
      await reload(); focusKeyword(k.id);
    } catch (e) { failed = e; throw e; } }, true);
    if (failed) throw failed;
  }
  function focusKeyword(id: string) { requestAnimationFrame(() => { const chip = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-keyword-id]')).find(el => el.dataset.keywordId === id); chip?.focus(); }); }
  function reveal(to: Destination) { setAxis('all'); setFilter('전체'); setQuery(''); setCollapsed(c => ({ ...c, [`all:${groupKey(to)}`]: false })); }
  async function move(k: Keyword | string, to: Destination) {
    const id = typeof k === 'string' ? k : k.id; if (!all.some(item => item.id === id)) return;
    let failed: unknown;
    await action(async () => { try { await postEvent(sid, { round, type: 'move', kwId: id, to }); await reload(); reveal(to); focusKeyword(id); } catch (e) { failed = e; throw e; } }, true);
    if (failed) throw failed;
  }
  async function add(word: string, to: Destination, origin: 'manual' | 'suggested') {
    if (lock.current) return false; let success = false;
    await action(async () => { try { const keyword = await addKeyword(sid, word, to, origin); setData(d => d ? { ...d, keywords: [...d.keywords, keyword] } : d); setDuplicate(null); setFilter('전체'); setQuery(''); success = true; }
      catch (e) { if (e instanceof KeywordApiError && e.duplicateOf) { const found = all.find(k => k.id === e.duplicateOf); setDuplicate(found ?? null); setError(found ? `이미 있는 키워드입니다. ${groupLabel(found)}의 “${found.kw}”을 확인하세요.` : '이미 있는 키워드입니다. 전체 목록을 확인하세요.'); } else throw e; }
    }); return success;
  }
  async function suggest(to: Destination) { let words: string[] = []; await action(async () => { words = (await suggestWords(sid, to)).words.map(w => w.word); }); return words; }
  async function draft() { if (!ui.canEdit) return; await action(async () => { await patchSession(sid, { drafts: { keywords: { [`r${round}`]: { round, gen: current?.gen ?? 0, decisions: decisions(), groups: custom } } } }); setDirty(false); setNotice('검토를 임시 저장했습니다. 저장하면 이 라운드를 확정합니다.'); }); }
  async function commit() { if (!current || !ui.canCommit) return; await action(async () => { await commitRound(sid, round, current.gen, decisions()); setOverrides({}); setDirty(false); await reload(); await patchSession(sid, { drafts: { keywords: { [`r${round}`]: null } } }); setNotice(`R${round}을 저장했습니다. 다음 작업을 선택하세요.`); }); }
  async function next() { if (!ui.canNext || dirty) return; if (round < 4) await generate(round + 1); else await action(async () => { await saveDirection(); await patchSession(sid, { step: 'crawl-setup' }); useSessionStore.getState().setSession({ step: 'crawl-setup' }); router.push('/pipeline/crawling'); }); }
  const approved = all.filter(k => k.status !== 'rejected'); const counts = axes.map(a => approved.filter(k => k.axis === a.value).length); const minimum = counts.indexOf(Math.min(...counts));
  if (!data) return <div className="space-y-4">{error ? <Banner tone="danger" actions={<Button onClick={() => window.location.reload()}>새로고침하기</Button>}>{error}</Banner> : <><p role="status">처리 중…</p><Skeleton height={120} /><Skeleton height={240} /></>}</div>;
  const steps = names.map((title, i) => ({ label: i < 4 ? `R${i + 1}` : '최종', title, description: techniques[i], state: i === (ui.final ? 4 : round - 1) ? 'current' : i < 4 && data.keywordRounds[String(i + 1)]?.committed ? 'complete' : 'upcoming' })) as [StepperItem, StepperItem, StepperItem, StepperItem, StepperItem];
  const reviewPanel = <>
        <div className="kw-filters"><ChoiceChips label="배지 필터" value={filter} onChange={v => setFilter(v as KeywordFilter)} options={keywordFilters.map(f => ({ value: f, label: `${f} ${filterKeywords(tabKeywords, f).length}` }))} /><Input label="키워드 검색" value={query} onChange={e => setQuery(e.target.value)} />{(filter !== '전체' || query) && <><span className="ds-t-caption">필터 적용 중</span><Button size="sm" onClick={() => { setFilter('전체'); setQuery(''); }}>해제하기</Button></>}<Popover triggerLabel="키보드 도움말 보기" label="키보드 단축키" open={help} onOpenChange={setHelp}><p>Tab 그룹 이동 · 방향키 칩 이동 · Home/End 처음/끝 · Enter/Space 거절 또는 복원 · M 이동 · Esc 취소</p></Popover><Button size="sm" onClick={() => { const close = !tabGroups.every(isCollapsed); setCollapsed(c => ({ ...c, ...Object.fromEntries(tabGroups.map(g => [`${axis}:${groupKey(g)}`, close])) })); }}>{tabGroups.every(isCollapsed) ? '모두 펼치기' : '모두 접기'}</Button></div>
        {!visible.length && <Banner>조건에 맞는 키워드가 없습니다. 필터를 해제하세요.</Banner>}
        {tabGroups.map(g => <KeywordGroup key={groupKey(g)} group={g} groups={groups} keywords={visible.filter(k => groupKey(k) === groupKey(g))} disabled={busy || !ui.canEdit} collapsed={isCollapsed(g)} toggle={() => setCollapsed(c => ({ ...c, [`${axis}:${groupKey(g)}`]: !isCollapsed(g) }))} onAdd={add} onSuggest={suggest} onMove={move} onReview={review} />)}
        <fieldset disabled={busy} className="kw-add"><Select label="새 하위 카테고리 축" value={customAxis} onChange={e => setCustomAxis(e.target.value)}><option value="">축 선택</option>{axes.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}</Select><Input label="새 하위 카테고리 이름" value={customName} onChange={e => setCustomName(e.target.value)} /><Button disabled={!customAxis || !customName.trim()} onClick={() => { const g = { axis: customAxis as Axis, sub: `custom:${customName.trim()}` }; if (!groups.some(v => groupKey(v) === groupKey(g))) { setCustom(c => [...c, g]); setDirty(true); } reveal(g); setCustomName(''); }}>하위 카테고리 추가하기</Button></fieldset>
  </>;
  return <div className="kw-screen"><StageVersionAction stage="stage1" /><div className="ds-eyebrow">1단계 · 키워드</div><h1 className={data.keywordRounds['2']?.committed ? 'ds-t-section' : 'ds-t-screen'}>{ui.final ? '최종 키워드를 검토합니다' : `R${round} ${names[round - 1]} 결과 ${ui.canEdit ? current?.keywords.length ?? 0 : 0}개를 검토합니다`}</h1><p>거절할 키워드를 누르고 사유를 남기면 다음 라운드에 반영됩니다. 드래그하거나 M 키로 하위 카테고리를 옮길 수 있습니다.</p><Stepper label="라운드 진행" steps={steps} />
    {error && <Banner tone="danger">{error}{duplicate && <Button size="sm" onClick={() => { reveal(duplicate); setDuplicate(null); }}>중복 키워드 확인하기</Button>}</Banner>}{notice && !readonly && <Banner>{notice}</Banner>}
    <div className="kw-layout"><div className="kw-main space-y-4"><Card><fieldset disabled={busy || running}><Input label="다음 라운드 방향 지시 (선택)" value={direction} onChange={e => setDirection(e.target.value)} placeholder="예: 영유아 관련 맥락을 더 발산해줘" /><div className="ds-actions"><Button disabled={!direction.trim()} onClick={() => void action(saveDirection)}>지시 저장하기</Button></div></fieldset></Card>
      {running ? <Card><p role="status" aria-live="polite">처리 중… R{round} 생성 중 · 보통 30~90초 · 경과 {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}</p><div className="space-y-4 mt-4">{[0, 1, 2].map(i => <Skeleton key={i} height={112} />)}</div><p className="ds-t-caption">다른 화면으로 이동해도 생성은 계속됩니다.</p></Card> : <>
      {current?.job.status === 'failed' && <Banner tone="danger" actions={<Button disabled={busy} onClick={() => void generate(round)}>다시 생성하기</Button>}>R{round} 생성에 실패했습니다(원인: {reasons[current.job.error?.kind ?? ''] ?? '생성 도구 오류'}). 승인한 키워드는 그대로 있습니다. 다시 생성하세요.{current.job.error?.kind === 'backend' && ' 설정에서 claude_api로 바꿀 수 있습니다.'}</Banner>}
      {current?.job.status === 'done' && !current.committed && (current?.keywords.length === 0 ? <Banner actions={<Button disabled={busy || !ui.canRegenerate} onClick={() => void generate(round, true)}>R{round} 다시 생성</Button>}>새 키워드가 나오지 않았습니다. 방향 지시를 바꾸거나 다시 생성하세요.</Banner> : current?.below_min ? <Banner actions={<Button disabled={busy || !ui.canRegenerate} onClick={() => void generate(round, true)}>R{round} 다시 생성</Button>}>목표 {current.below_min.min}개 중 {current.below_min.got}개가 생성되었습니다. 그대로 검토하거나 다시 생성하세요.</Banner> : null)}
      {ui.canEdit && <Card><Tabs label="3축" value={axis} onChange={setAxis} items={[{ value: 'all', label: '전체' }, ...axes].map(a => ({ ...a, count: all.filter(k => a.value === 'all' || k.axis === a.value).length, content: a.value === axis ? reviewPanel : null }))} />

      </Card>}</>}
    </div><aside className="kw-side space-y-4"><Card><h2 className="ds-t-card">축 분포</h2><p className="ds-t-caption">승인 예정 포함 {approved.length}개 기준 · 부족한 축은 다음 라운드가 채웁니다.</p><BarList max={Math.max(1, approved.length)} highlightIndex={minimum} items={axes.map((a, i) => ({ label: a.label, value: counts[i], displayValue: `${counts[i]}개 · ${approved.length ? Math.round(counts[i] / approved.length * 100) : 0}%` }))} /></Card>
    {!data.keywordRounds['2']?.committed && <Card><h2 className="ds-t-card">커버리지</h2><Badge>R2 확정 후 계산</Badge></Card>}
    {INTERNAL_TOOLS && <Card><details><summary>keyword_feedback.md 미리보기 <Badge>내부용</Badge></summary><pre className="ds-t-caption">{data.feedback_md || '아직 기록된 피드백이 없습니다.'}</pre></details></Card>}</aside></div>
    {data.keywordRounds['2']?.committed && <section className="mt-6" aria-label="커버리지 검사"><CoveragePanel coverage={data.coverage} busy={busy || running} onRefresh={() => void action(async () => { await getCoverage(sid); await reload(); })} /></section>}
    <p className="ds-t-caption" aria-live="polite">승인 예정 {approved.length} · 거절 {all.length - approved.length}</p>
    <SaveBar dirty={dirty || !!direction.trim()} valid={ui.canCommit && !busy} saving={busy} onDraft={() => void draft()} onSave={() => void commit()} primary={<><Button disabled={!ui.canStart || busy || (dirty && !!current)} onClick={() => void generate(round)}>{ui.final ? '추가 생성하기' : current?.job.status === 'failed' ? '다시 생성하기' : '생성하기'}</Button><Button variant="primary" disabled={!ui.canNext || busy || dirty} onClick={() => void next()}>{round === 4 ? '크롤링 설정하기' : '다음 라운드 생성'}</Button></>} />
  </div>;
}
