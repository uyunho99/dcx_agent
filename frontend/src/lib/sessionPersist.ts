import { getSession } from "@/lib/api";
import type { Keyword, SessionData } from "@/lib/types";

const STORAGE_KEY = "dcx_active_session";

interface PersistedSession {
  sid: string;
  step: string;
}

export function persistSid(sid: string, step: string) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sid, step }));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function getPersistedSid(): PersistedSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.sid === "string") return parsed as PersistedSession;
    return null;
  } catch {
    return null;
  }
}

export function clearPersistedSid() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

interface StoreSetter {
  setSession: (data: Record<string, unknown>) => void;
}

export async function restoreSessionToStore(
  sid: string,
  store: StoreSetter,
): Promise<string> {
  const resp = await getSession(sid);
  const d = (resp.data || resp) as Record<string, unknown>;
  const step = (d.step as string) || "start";
  store.setSession({
    sid,
    bk: (d.bk as string) || "",
    pd: (d.problemDef as string) || "",
    kw: (d.allKw as Keyword[]) || [],
    sd: d as SessionData,
    ages: (d.ages as string[]) || [],
    ar: (d.ageRange as string[]) || [],
    gens: (d.gens as string[]) || [],
    step,
    pendingKw: (d._pendingKw as Keyword[]) || [],
    lastRound: (d._lastRound as string) || "",
  });
  return step;
}
