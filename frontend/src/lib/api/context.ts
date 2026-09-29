import type { ProjectContext, SessionInfo } from "@/lib/types";
const API = process.env.NEXT_PUBLIC_API_URL || "";
export async function contextRequest<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, { method, headers: { "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok || data.status === "error" || data.status === "not_found") throw new Error(data.error?.message || "요청에 실패했습니다");
  return data as T;
}
export const createContext = (context: ProjectContext) => contextRequest<{sid: string}>("/context", "POST", context);
export const getContext = (sid: string) => contextRequest<{projectContext: ProjectContext; draft?: ProjectContext | null}>(`/context/${encodeURIComponent(sid)}`);
export const putContext = (sid: string, context: ProjectContext) => contextRequest<{projectContext: ProjectContext; warnings: string[]}>(`/context/${encodeURIComponent(sid)}`, "PUT", context);
export const patchSession = (sid: string, patch: {step?: string; drafts?: Record<string, unknown>}) => contextRequest(`/session/${encodeURIComponent(sid)}`, "PATCH", patch);
export const suggestCategory = (bk: string, oneLiner: string) => contextRequest<ProjectContext["productCategory"]>("/context/category-suggest", "POST", {bk, oneLiner});
export const contextSessions = () => contextRequest<{sessions: SessionInfo[]}>("/sessions");
