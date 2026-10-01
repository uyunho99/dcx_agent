'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { create } from 'zustand';
import { resolveVersionSelection } from '@/lib/logic/versionSelection';
import { Banner, Button } from '@/components/ds';
import { useSessionStore } from '@/stores/useSessionStore';
import { getVersionSession, listVersions, type VersionList, type VersionSession } from '@/lib/api/versions';

import { refreshSessionAfterStage as refreshStageSession } from '@/lib/refreshSessionAfterStage';

import { useDirty } from "../DirtyProvider";
// Session-scoped UI selection survives stage navigation, without changing server activation.
const useSelection = create<{sid: string | null; version?: string; select: (sid: string, version: string) => void}>(set => ({ sid: null, select: (sid, version) => set({sid, version}) }));
type State = { refreshSessionAfterStage: () => Promise<void>; sid: string | null; version?: string; readonly: boolean; meta: VersionList | null; session: VersionSession | null; select: (version: string, confirmed?: boolean) => void; loading: boolean; error: string; retry: () => void; newerVersion?: string; conflict?: boolean; openActive?: () => Promise<void> };
const Context = createContext<State>({refreshSessionAfterStage: async () => {}, sid: null, readonly: false, meta: null, session: null, select: () => {}, loading: false, error: '', retry: () => {}});
export const useVersion = () => useContext(Context);
export function VersionProvider({children}: {children: ReactNode}) {
  const {confirmNavigation} = useDirty();
  const sid = useSessionStore(s => s.sid); const schema = useSessionStore(s => s.sd?.schemaVersion);
  const stageRevision = useRef(0);
  const [conflict, setConflict] = useState(false);
  const selection = useSelection(); const requested = selection.sid === sid ? selection.version : undefined;
  const [loaded, setLoaded] = useState<{sid: string; requested?: string; meta: VersionList; session: VersionSession} | null>(null);
  const [failure, setFailure] = useState<{sid: string; requested?: string; message: string} | null>(null); const [retry, setRetry] = useState(0);
  useEffect(() => {const onConflict = () => {setConflict(true); setRetry(n => n + 1);}; window.addEventListener("dcx-version-conflict", onConflict); return () => window.removeEventListener("dcx-version-conflict", onConflict);}, []);
  useEffect(() => {
    if (!sid || schema !== 2) return;
    let cancelled = false;
    async function read() {
      const revision = stageRevision.current;
      try {
        const meta = await listVersions(sid!);
        const {version} = resolveVersionSelection(requested, meta);
        const {data} = await getVersionSession(sid!, version);
        if (!cancelled && revision === stageRevision.current) {
          if (!requested) useSelection.getState().select(sid!, version);
          setLoaded({sid: sid!, requested: version, meta, session: data}); setFailure(null);
        }
      } catch { if (!cancelled && revision === stageRevision.current) setFailure({sid: sid!, requested, message: '버전을 불러오지 못했습니다. 다시 확인하세요.'}); }
    }
    void read(); const timer = setInterval(read, 10000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [sid, schema, requested, retry]);
  const ready = loaded?.sid === sid && loaded?.requested === requested;
  const meta = loaded?.sid === sid ? loaded.meta : null; const session = ready ? loaded.session : null;
  const version = requested ?? meta?.activeVersion;
  const readonly = !!meta && (version !== meta.activeVersion || !!meta.versions.find(v => v.id === version)?.readonly);
  const current = useRef<{sid: string | null; version?: string; readonly: boolean} | null>(null);
  useEffect(() => {
    current.current = {sid, version, readonly};
    return () => { current.current = null; };
  }, [sid, version, readonly]);
  const refreshSessionAfterStage = useCallback(async () => {
    const target = current.current;
    const isCurrent = () => !!target && current.current === target && !target.readonly
      && useSessionStore.getState().sid === sid
      && useSelection.getState().version === version;
    if (!sid || readonly || !isCurrent()) return;
    // Discard background reads that began before this completion refresh.
    stageRevision.current++;
    try {
      await refreshStageSession(sid, version, data => {
        stageRevision.current++;
        setLoaded(previous => previous?.sid === sid && previous.requested === version
          ? {...previous, session: data} : previous);
        setFailure(null);
      }, isCurrent);
    } catch (cause) {
      if (isCurrent()) setFailure({sid, requested: version, message: '버전을 불러오지 못했습니다. 다시 확인하세요.'});
      throw cause;
    }
  }, [sid, version, readonly]);
  const select = (v: string, confirmed = false) => { if (sid && (confirmed || confirmNavigation())) { selection.select(sid, v); setConflict(false); } };
  const error = failure?.sid === sid && failure?.requested === requested ? failure.message : '';
  const newerVersion = meta ? resolveVersionSelection(version, meta).newerVersion : undefined;
  return <Context.Provider value={{refreshSessionAfterStage, sid, version, readonly, meta, session, select, loading: !!sid && schema === 2 && !ready, error, retry: () => {setFailure(null); setRetry(n => n + 1);}, newerVersion, conflict, openActive: async () => {if(!sid) return; try {const latest = await listVersions(sid); select(latest.activeVersion);} catch {setFailure({sid, requested, message:'활성 버전을 불러오지 못했습니다. 다시 확인하세요.'});}}}}>{children}</Context.Provider>;
}

// Only the main content is gated/remounted; shell controls retain their state.
export function VersionContent({children}: {children: ReactNode}) {
  const view = useVersion();
  const error = view.error && <Banner tone="danger" actions={<Button onClick={view.retry}>다시 확인하기</Button>}>{view.error}</Banner>;
  if (view.loading) return error || <p role="status">처리 중…</p>;
  return <>{view.conflict && <Banner tone="warning" actions={<Button onClick={() => void view.openActive?.()}>활성 버전 열기</Button>}>다른 버전이 활성화되었습니다. 입력값은 그대로 있습니다. 활성 버전을 열어 확인하세요.</Banner>}{error}<div key={`${view.sid}:${view.version ?? ''}`}>{children}</div></>;
}
