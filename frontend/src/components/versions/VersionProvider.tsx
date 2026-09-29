'use client';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { create } from 'zustand';
import { Banner, Button } from '@/components/ds';
import { useSessionStore } from '@/stores/useSessionStore';
import { getVersionSession, listVersions, type VersionList, type VersionSession } from '@/lib/api/versions';

// Session-scoped UI selection survives stage navigation, without changing server activation.
const useSelection = create<{sid: string | null; version?: string; select: (sid: string, version: string) => void}>(set => ({ sid: null, select: (sid, version) => set({sid, version}) }));
type State = { sid: string | null; version?: string; readonly: boolean; meta: VersionList | null; session: VersionSession | null; select: (version: string) => void };
const Context = createContext<State>({sid: null, readonly: false, meta: null, session: null, select: () => {}});
export const useVersion = () => useContext(Context);
export function VersionProvider({children}: {children: ReactNode}) {
  const sid = useSessionStore(s => s.sid); const schema = useSessionStore(s => s.sd?.schemaVersion);
  const selection = useSelection(); const requested = selection.sid === sid ? selection.version : undefined;
  const [loaded, setLoaded] = useState<{sid: string; requested?: string; meta: VersionList; session: VersionSession} | null>(null);
  const [error, setError] = useState(''); const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!sid || schema !== 2) return;
    let cancelled = false;
    async function read() {
      try {
        const meta = await listVersions(sid!);
        const {data} = await getVersionSession(sid!, requested ?? meta.activeVersion);
        if (!cancelled) { setLoaded({sid: sid!, requested, meta, session: data}); setError(''); }
      } catch { if (!cancelled) setError('버전을 불러오지 못했습니다. 다시 확인하세요.'); }
    }
    void read(); const timer = setInterval(read, 10000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [sid, schema, requested, retry]);
  const ready = loaded?.sid === sid && loaded?.requested === requested;
  const meta = ready ? loaded.meta : null; const session = ready ? loaded.session : null;
  const version = requested ?? meta?.activeVersion;
  const readonly = !!meta && (version !== meta.activeVersion || !!meta.versions.find(v => v.id === version)?.readonly);
  const select = (v: string) => { if (sid) selection.select(sid, v); };
  return <Context.Provider value={{sid, version, readonly, meta, session, select}}>{sid && schema === 2 && !ready ? error ? <Banner tone="danger" actions={<Button onClick={() => setRetry(n => n + 1)}>다시 확인하기</Button>}>{error}</Banner> : <p role="status">처리 중…</p> : <div key={`${sid}:${version ?? ''}`}>{children}</div>}</Context.Provider>;
}
