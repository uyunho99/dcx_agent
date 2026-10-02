'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, Banner, Button, Card, ProgressBar } from '../ds';
import { ProvisionalBadge } from '../ds/ProvisionalBadge';
import { StageVersionAction, VersionStage } from '../versions/StageVersion';
import { useVersion } from '../versions/VersionProvider';
import { useStageCompletionRefresh } from '../versions/useStageCompletionRefresh';
import { usePolling } from '@/lib/usePolling';
import { getVersionSession } from '@/lib/api/versions';
import { patchSession } from '@/lib/api/context';
import * as api from '@/lib/api/segment';
import type { SegmentCluster, SegmentContext, SegmentDraft, SegmentKSuggest, SegmentPersona, SegmentPersonaConfirmation, SegmentStatus } from '@/lib/types';
import { LayerTabs, type SegmentLayer } from './LayerTabs';
import { ClusterLayer, type Edit } from './ClusterLayer';
import { PersonaLayer } from './PersonaLayer';
import { ContextLayer } from './ContextLayer';
import { KSuggestChart } from './KSuggestChart';
import { canStartEvidence, currentSegmentDraft, layerState, segmentErrorMessage, segmentErrorMessages } from './segmentView';
const running = (s: SegmentStatus | null) => !!s && ['queued', 'running', 'paused'].includes(s.status);
const steps = [['load', '적재'], ['L1', 'Cluster'], ['L2', 'Persona'], ['L3', 'Context'], ['quality', '품질'], ['dims', '경험 차원'], ['drafts', '초안']];
type Props = {
    sid: string;
    version?: string;
    readonly?: boolean;
    draft?: SegmentDraft | null;
};
export function SegmentScreen({ sid, version, readonly = false }: Props) {
    const view = useVersion();
    const [status, setStatus] = useState<SegmentStatus | null>(null);
    const [layer, setLayer] = useState<SegmentLayer>('6-A');
    const [clusters, setClusters] = useState<SegmentCluster[]>([]);
    const [personas, setPersonas] = useState<SegmentPersona[]>([]);
    const [contexts, setContexts] = useState<SegmentContext[]>([]);
    const [suggest, setSuggest] = useState<SegmentKSuggest | null>(null);
    const [selected, setSelected] = useState('');
    const [k, setK] = useState(5);
    const [edits, setEdits] = useState<Record<string, Edit>>({});
    const [emptyRatio, setEmptyRatio] = useState(0);
    const [error, setError] = useState('');
    const [pollError, setPollError] = useState('');
    const [notice, setNotice] = useState('');
    const [savedDraft, setSavedDraft] = useState<SegmentDraft | null>();
    const [busy, setBusy] = useState(false);
    const [loaded, setLoaded] = useState(false);
    const [resetOpen, setResetOpen] = useState(false);
    const resetPanel = useRef<HTMLDivElement | null>(null);
    const resetTrigger = useRef<HTMLButtonElement | null>(null);
    useEffect(() => { if (resetOpen)
        resetPanel.current?.focus(); }, [resetOpen]);
    function closeReset() { setResetOpen(false); resetTrigger.current?.focus(); }
    const draftWrite = useRef<Promise<unknown>>(Promise.resolve());
    const statusEpoch = useRef(0);
    const lock = useRef(false);
    const epoch = useRef(0);
    const active = useRef(true);
    const runRef = useRef<string | null>(null);
    const kRun = useRef<string | null>(null);
    const loadedStatus = useRef<SegmentStatus | null>(null);
    const editorRoot = useRef<HTMLDivElement | null>(null);
    const focusAfterSave = useRef<HTMLElement | null>(null);
    useEffect(() => {
        if (!busy && focusAfterSave.current) {
            const next = editorRoot.current?.querySelector<HTMLElement>('[data-forward]:not(:disabled)');
            (next ?? focusAfterSave.current).focus();
            focusAfterSave.current = null;
        }
    }, [busy]);
    const readDraft = useCallback(async () => {
        const session = await getVersionSession(sid, version);
        if (active.current) setSavedDraft(session.data.drafts?.segment as SegmentDraft ?? null);
    }, [sid, version]);
    useEffect(() => {
        void readDraft().catch(e => { if (active.current) setError(segmentErrorMessage(e)); });
    }, [readDraft]);
    const draftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    useEffect(() => { active.current = true; return () => { active.current = false; if (draftTimer.current)
        clearTimeout(draftTimer.current); }; }, []);
    const fetcher = useCallback(async () => {
        const generation = statusEpoch.current;
        try {
            const result = await api.getSegmentStatus(sid, version);
            if (!active.current || generation !== statusEpoch.current)
                throw new Error('Obsolete status response');
            setPollError('');
            if (!running(result)) setNotice('');
            return result;
        }
        catch (e) {
            if (active.current && generation === statusEpoch.current)
                setPollError(segmentErrorMessage(e));
            throw e;
        }
    }, [sid, version]);
    const stop = useCallback((s: SegmentStatus) => !running(s), []);
    const poll = usePolling({ fetcher, interval: 3000, enabled: !readonly && (!status || running(status)), shouldStop: stop });
    useEffect(() => { if (poll.data)
        setStatus(poll.data); }, [poll.data]);
    const current = status ?? poll.data;
    useStageCompletionRefresh(current?.status === 'done' ? current.run : null);
    const load = useCallback(async (s: SegmentStatus) => {
        const token = ++epoch.current;
        loadedStatus.current = s;
        try {
            const a = await api.getSegmentClusters(sid, version);
            const gates = layerState(s);
            const b = !gates.personas.locked ? await api.getSegmentPersonas(sid, undefined, version) : null;
            const c = !gates.personas.locked && !gates.contexts.locked ? await api.getSegmentContexts(sid, undefined, version) : null;
            if (!active.current || token !== epoch.current)
                return;
            if ([a, b, c].some(result => result && result.run !== s.run))
                throw new Error(segmentErrorMessages.stale_run);
            setClusters(a.clusters);
            setSuggest(a.kSuggest);
            if (kRun.current !== s.run) {
                kRun.current = s.run;
                setK(a.kSuggest?.k ?? 5);
            }
            setPersonas(b?.personas ?? []);
            setContexts(c?.contexts ?? []);
            setEmptyRatio(c?.emptyGoalConstraintRatio ?? 0);
            setLoaded(true);
        }
        catch (e) {
            if (active.current && token === epoch.current)
                setError(segmentErrorMessage(e));
        }
    }, [sid, version]);
    useEffect(() => {
        if (!current || savedDraft === undefined)
            return;
        if (runRef.current !== current.run) {
            runRef.current = current.run;
            setLoaded(false);
            if (draftTimer.current) clearTimeout(draftTimer.current);
            setLayer('6-A');
            setSelected('');
            setClusters([]);
            setPersonas([]);
            setContexts([]);
            const saved = currentSegmentDraft(savedDraft, current.run);
            setEdits(saved && typeof saved.edits === 'object' && saved.edits !== null ? saved.edits as Record<string, Edit> : {});
        }
        if (!running(current) && current.run && ['review', 'done'].includes(current.status) && loadedStatus.current !== current)
            void load(current);
    }, [current, load, savedDraft]);
    const blocked = readonly || !!view.conflict || busy || running(current) || !current || !!error || !!pollError || savedDraft === undefined;
    const evidence = current ? canStartEvidence(current) : { allowed: false, reason: '다음 묶음에서 열립니다' };
    async function refresh() {
        if (lock.current) return;
        setError('');
        if (savedDraft === undefined) {
            try { await readDraft(); }
            catch (e) { setError(segmentErrorMessage(e)); return; }
        }
        loadedStatus.current = null;
        try { setStatus(await fetcher()); }
        catch { /* fetcher displays a recoverable poll error */ }
    }
    function edit(id: string, value: Edit) { if (blocked)
        return; const next = { ...edits, [id]: { ...edits[id], ...value } }; setEdits(next); if (draftTimer.current)
        clearTimeout(draftTimer.current); const run = current?.run; draftTimer.current = setTimeout(() => { if (!run || runRef.current !== run || !active.current)
        return; draftWrite.current = draftWrite.current.catch(() => { }).then(() => patchSession(sid, { drafts: { segment: { run, edits: next } } }, version)); void draftWrite.current.catch(e => { if (active.current && runRef.current === run)
        setError(segmentErrorMessage(e)); }); }, 600); }
    async function mutate(work: () => Promise<unknown>, ids: string[] = []) {
        if (blocked || lock.current)
            return;
        lock.current = true;
        if (typeof document !== 'undefined' && editorRoot.current?.contains(document.activeElement))
            focusAfterSave.current = document.activeElement as HTMLElement;
        statusEpoch.current++;
        setBusy(true);
        setError('');
        if (draftTimer.current)
            clearTimeout(draftTimer.current);
        try {
            await draftWrite.current.catch(() => { });
            await work();
            if (!active.current)
                return;
            const remaining = Object.fromEntries(Object.entries(edits).filter(([id]) => !ids.includes(id)));
            if (current?.run)
                await patchSession(sid, { drafts: { segment: { run: current.run, edits: remaining } } }, version);
            const next = await fetcher();
            if (active.current) {
                if (next.run === runRef.current) await load(next);
                setEdits(remaining);
                setStatus(next);
                await view.refreshSessionAfterStage();
            }
        }
        catch (e) {
            if (active.current)
                setError(segmentErrorMessage(e));
        }
        finally {
            lock.current = false;
            if (active.current)
                setBusy(false);
        }
    }
    function confirm(id: string) {
        const run = current?.run;
        if (!run || !loaded)
            return;
        const e = edits[id];
        if (layer === '6-A') {
            const row = clusters.find(c => c.id === id)!;
            const name = e?.name ?? row.name ?? row.nameDraft ?? '';
            if (!name.trim())
                return;
            void mutate(() => api.confirmSegmentCluster(sid, id, { run, name, confirm: true }, version), [id]);
        }
        if (layer === '6-B') {
            const row = personas.find(p => p.id === id)!;
            const name = e?.name ?? row.name ?? row.nameDraft ?? '';
            const desire = e?.desire ?? row.desire ?? row.desireDraft ?? '';
            const goals = e?.goals ?? (row.goals.length ? row.goals : row.goalsDraft);
            if (!name.trim() || !desire.trim() || !goals.length || goals.length > 3 || goals.some(g => !g.trim()))
                return;
            void mutate(() => api.confirmSegmentPersona(sid, id, { run, name, desire, goals: goals as SegmentPersonaConfirmation['goals'], confirm: true }, version), [id]);
        }
        if (layer === '6-C') {
            const row = contexts.find(c => c.id === id)!;
            const name = e?.name ?? row.name ?? row.nameDraft ?? '';
            const action = e?.action ?? row.action ?? row.actionDraft ?? '';
            if (!name.trim() || !action.trim())
                return;
            void mutate(() => api.confirmSegmentContext(sid, id, { run, name, action, confirm: true }, version), [id]);
        }
    }
    async function start(reset = false) {
        if (blocked || lock.current)
            return;
        lock.current = true;
        statusEpoch.current++;
        setBusy(true);
        if (draftTimer.current)
            clearTimeout(draftTimer.current);
        epoch.current++;
        try {
            await draftWrite.current.catch(() => { });
            const result = await api.startSegment(sid, reset ? { k, confirmReset: true } : {}, version);
            if (active.current) {
                setResetOpen(false);
                setEdits({});
                setLoaded(false);
                setStatus({ run: result.runId, status: 'running', step: 'load', progress: 0, confirm: { clusters: '0/0', personas: '0/0', contexts: '0/0' } });
                poll.refresh();
            }
        }
        catch (e) {
            if (active.current) {
                const message = segmentErrorMessage(e);
                if (message === segmentErrorMessages.running) {
                    setNotice(message);
                    setResetOpen(false);
                    // Observe the existing worker even if the first status retry fails.
                    setStatus(previous => previous ? { ...previous, status: 'running' } : previous);
                    try { setStatus(await fetcher()); } catch { /* polling retries */ }
                } else setError(message);
            }
        }
        finally {
            lock.current = false;
            if (active.current)
                setBusy(false);
        }
    }
    const chosen = personas.find(p => p.id === selected) ?? personas[0];
    const visibleContexts = contexts.filter(c => c.personaId === chosen?.id);
    function bulk() { const run = current?.run; if (!run || !chosen || !visibleContexts.length)
        return; const items = visibleContexts.map(c => ({ id: c.id, name: edits[c.id]?.name ?? c.name ?? c.nameDraft ?? '', action: edits[c.id]?.action ?? c.action ?? c.actionDraft ?? '' })); if (items.some(i => !i.name.trim() || !i.action.trim()))
        return; void mutate(() => api.confirmSegmentContexts(sid, chosen.id, { run, contexts: items }, version), items.map(i => i.id)); }
    const gates = current ? layerState(current) : null;
    const forward = loaded && !running(current) && (layer === '6-A'
        ? !gates?.personas.locked && !clusters.some(c => !c.confirmed || edits[c.id])
        : layer === '6-B' && !gates?.contexts.locked && !personas.some(p => !p.confirmed || edits[p.id]));
    const displayedError = error || pollError;
    const editor = { disabled: blocked || !loaded, edits, onEdit: edit, onConfirm: confirm };
    return <VersionStage stage="stage6" showBanner={false}><div ref={editorRoot} className="min-w-0 space-y-5 break-words"><StageVersionAction stage="stage6"/><header><p className="ds-eyebrow">6단계 · 클러스터링</p><h1 className="ds-t-screen">{layer === '6-A' ? 'Touch Point를 확정합니다' : layer === '6-B' ? 'Persona의 Desire를 확정합니다' : 'Context 이름과 행동을 확정합니다'}</h1><p className="ds-t-body">Cluster → Persona → Context 순서로 초안을 확인하고 확정하세요.</p><ProvisionalBadge /></header>{notice && <Banner>{notice}</Banner>}{displayedError && <Banner tone="danger" actions={<Button onClick={() => void refresh()}>새로고침</Button>}>{displayedError}{displayedError !== segmentErrorMessages.stale_run && ' 입력은 유지됩니다.'}</Banner>}{Array.isArray(current?.stage6?.warnings) && current.stage6.warnings.map((warning, i) => typeof warning === 'object' && warning !== null && 'message' in warning ? <Banner key={i} tone="warning">{String(warning.message)}</Banner> : null)}{current?.reason && <Banner tone="warning">{current.reason}</Banner>}{current && <LayerTabs value={layer} confirm={current.confirm} onChange={next => { if (running(current))
        return; const gates = layerState(current); if (next === '6-B' && gates.personas.locked || next === '6-C' && (gates.personas.locked || gates.contexts.locked))
        return; setLayer(next); }}/>}
 {current?.run && !running(current) && layer === '6-A' && <><div className="flex flex-wrap items-center gap-3"><label>클러스터 수 k<select aria-label="클러스터 수 k" className="ds-inp" disabled={blocked} value={k} onChange={e => setK(Number(e.target.value))}>{[3, 4, 5, 6, 7, 8].map(n => <option key={n}>{n}</option>)}</select></label><button ref={resetTrigger} type="button" className="ds-btn ds-secondary" disabled={blocked} aria-haspopup="dialog" aria-expanded={resetOpen} onClick={() => setResetOpen(true)}>다시 나누기</button></div>{resetOpen && <div ref={resetPanel} className="ds-card space-y-3" tabIndex={-1} role="dialog" aria-modal="false" aria-label="다시 나누기 확인" onKeyDown={e => { if (e.key === 'Escape') {
        e.preventDefault();
        closeReset();
    } }}><p>이름 · Desire · Context 확정이 모두 지워집니다.</p><Button disabled={blocked} onClick={() => void start(true)}>확인하고 다시 나누기</Button><Button disabled={busy} onClick={closeReset}>취소</Button></div>}</>}
 {!current ? <Card><p role="status">클러스터링 정보를 불러오는 중…</p></Card> : running(current) ? <Card className="space-y-4"><h2 className="ds-t-card">6단계 · 실행 중</h2><p aria-live="polite">{`${current.step} · ${steps.find(([key]) => key === current.step)?.[1] ?? ''} ${current.status === 'paused' ? '일시 정지' : '진행 중'} ${Math.round(current.progress * 100)}%`}</p><ol className="grid grid-cols-4 gap-3">{steps.map(([key, label], i) => { const position = steps.findIndex(([k]) => k === current.step); return <li key={key}><Badge>{i < position ? '완료' : i === position ? '진행 중' : '대기'}</Badge><p>{label}</p></li>; })}</ol><ProgressBar label="클러스터링 진행" value={current.progress * 100}/><p>화면을 닫아도 계속됩니다.</p><Button disabled>다시 나누기</Button></Card> : !current.run || !['review', 'done'].includes(current.status) ? <Card className="space-y-4"><p>학습 결과의 Core · Supporting 문서를 나눕니다.</p><Button variant="primary" disabled={blocked} onClick={() => void start()}>{current.status === 'failed' || current.status === 'interrupted' ? '이어서 진행' : '클러스터링 실행'}</Button></Card> : !loaded ? <Card><p role="status">결과를 불러오는 중…</p></Card> : <>
 {layer === '6-A' && <>{suggest && <details><summary className="cursor-pointer">k 제안 근거 보기</summary><div className="max-w-sm"><KSuggestChart k={suggest.suggested} silhouette={suggest.silhouette} sample={suggest.sample}/></div></details>}{clusters.length ? <ClusterLayer {...editor} clusters={clusters} onRequest={(id, kind, note) => void mutate(() => api.createSegmentRequest(sid, { layer: 'clusters', id, kind, note }, version))}/> : <Card>클러스터링할 문서가 없습니다.</Card>}</>}
 {layer === '6-B' && <PersonaLayer {...editor} forwardPrimary={!!forward} personas={personas} clusters={clusters} selected={chosen?.id ?? ''} onSelect={setSelected}/>}
 {layer === '6-C' && <div className="grid grid-cols-[minmax(160px,1fr)_minmax(0,3fr)] gap-5"><nav aria-label="Persona 목록" className="min-w-0 space-y-2">{personas.map(p => { const rows = contexts.filter(c => c.personaId === p.id); return <Button key={p.id} className="w-full whitespace-normal text-left" aria-current={chosen?.id === p.id ? 'true' : undefined} onClick={() => setSelected(p.id)}>{p.clusterId} · {p.name ?? p.nameDraft ?? p.id} · {rows.filter(c => c.confirmed).length}/{rows.length} 확정</Button>; })}</nav><ContextLayer {...editor} contexts={visibleContexts} emptyRatio={emptyRatio} onBulk={bulk}/></div>}
 {forward && <div className="flex justify-end"><Button data-forward variant="primary" disabled={blocked} onClick={() => setLayer(layer === '6-A' ? '6-B' : '6-C')}>{layer === '6-A' ? '6-B로 →' : '6-C로 →'}</Button></div>}
 <p aria-live="polite">{layer === '6-A' ? current.confirm.clusters : layer === '6-B' ? current.confirm.personas : current.confirm.contexts} 확정</p></>}
 <div className="flex justify-end"><Button disabled={!evidence.allowed} title={evidence.reason}>근거 탐색 실행</Button></div></div></VersionStage>;
}
