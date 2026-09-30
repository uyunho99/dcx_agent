import { getSession } from "@/lib/api";
import type { Keyword, SessionData, ProjectContext } from "@/lib/types";

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
  if (resp.status !== "ok" || !resp.data) throw new Error("세션을 불러오지 못했습니다");
  const context = d.projectContext as ProjectContext | undefined;
  const pending = (d.drafts as {keywords?: {pendingKw?: Keyword[]; lastRound?: string}} | undefined)?.keywords;
  const step = (d.step as string) || "start";
  store.setSession({
    sid,
    projectContext: context ?? null,
    bk: (d.bk as string) || "",
    pd: (d.problemDef as string) || "",
    kw: (d.allKw as Keyword[]) || [],
    sd: d as SessionData,
    ages: (d.ages as string[]) || [],
    ar: (d.ageRange as string[]) || [],
    gens: (d.gens as string[]) || [],
    step,
    pendingKw: pending?.pendingKw || (d._pendingKw as Keyword[]) || [],
    lastRound: pending?.lastRound || (d._lastRound as string) || "",
  });
  return step;
}
