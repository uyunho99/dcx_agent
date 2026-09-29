'use client';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { create } from 'zustand';
import { resolveVersionSelection } from '@/lib/logic/versionSelection';
import { Banner, Button } from '@/components/ds';
import { useSessionStore } from '@/stores/useSessionStore';
import { getVersionSession, listVersions, type VersionList, type VersionSession } from '@/lib/api/versions';

// Session-scoped UI selection survives stage navigation, without changing server activation.
const useSelection = create<{sid: string | null; version?: string; select: (sid: string, version: string) => void}>(set => ({ sid: null, select: (sid, version) => set({sid, version}) }));
type State = { sid: string | null; version?: string; readonly: boolean; meta: VersionList | null; session: VersionSession | null; select: (version: string) => void; loading: boolean; error: string; retry: () => void; newerVersion?: string };
const Context = createContext<State>({sid: null, readonly: false, meta: null, session: null, select: () => {}, loading: false, error: '', retry: () => {}});
export const useVersion = () => useContext(Context);
export function VersionProvider({children}: {children: ReactNode}) {
  const sid = useSessionStore(s => s.sid); const schema = useSessionStore(s => s.sd?.schemaVersion);
  const selection = useSelection(); const requested = selection.sid === sid ? selection.version : undefined;
  const [loaded, setLoaded] = useState<{sid: string; requested?: string; meta: VersionList; session: VersionSession} | null>(null);
  const [failure, setFailure] = useState<{sid: string; requested?: string; message: string} | null>(null); const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!sid || schema !== 2) return;
    let cancelled = false;
    async function read() {
      try {
        const meta = await listVersions(sid!);
        const {version} = resolveVersionSelection(requested, meta);
        const {data} = await getVersionSession(sid!, version);
        if (!cancelled) {
          if (!requested) useSelection.getState().select(sid!, version);
          setLoaded({sid: sid!, requested: version, meta, session: data}); setFailure(null);
        }
      } catch { if (!cancelled) setFailure({sid: sid!, requested, message: '버전을 불러오지 못했습니다. 다시 확인하세요.'}); }
    }
    void read(); const timer = setInterval(read, 10000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [sid, schema, requested, retry]);
  const ready = loaded?.sid === sid && loaded?.requested === requested;
  const meta = loaded?.sid === sid ? loaded.meta : null; const session = ready ? loaded.session : null;
  const version = requested ?? meta?.activeVersion;
  const readonly = !!meta && (version !== meta.activeVersion || !!meta.versions.find(v => v.id === version)?.readonly);
  const select = (v: string) => { if (sid) selection.select(sid, v); };
  const error = failure?.sid === sid && failure?.requested === requested ? failure.message : '';
  const newerVersion = meta ? resolveVersionSelection(version, meta).newerVersion : undefined;
  return <Context.Provider value={{sid, version, readonly, meta, session, select, loading: !!sid && schema === 2 && !ready, error, retry: () => {setFailure(null); setRetry(n => n + 1);}, newerVersion}}>{children}</Context.Provider>;
}

// Only the main content is gated/remounted; shell controls retain their state.
export function VersionContent({children}: {children: ReactNode}) {
  const view = useVersion();
  const error = view.error && <Banner tone="danger" actions={<Button onClick={view.retry}>다시 확인하기</Button>}>{view.error}</Banner>;
  if (view.loading) return error || <p role="status">처리 중…</p>;
  return <>{error}<div key={`${view.sid}:${view.version ?? ''}`}>{children}</div></>;
}
