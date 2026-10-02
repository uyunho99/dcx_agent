import type { ProjectContext, SessionInfo } from "@/lib/types";
import { ApiError, responseError, versionQuery } from "./errors";
const API = process.env.NEXT_PUBLIC_API_URL || "";
export async function contextRequest<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, { method, headers: { "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok || data.status === "error" || data.status === "not_found") throw new ApiError(responseError(data, response.status), data.error?.kind ?? data.error?.code, response.status);
  return data as T;
}
export const createContext = (context: ProjectContext) => contextRequest<{sid: string}>("/context", "POST", context);
export const getContext = (sid: string) => contextRequest<{projectContext: ProjectContext; draft?: ProjectContext | null}>(`/context/${encodeURIComponent(sid)}`);
export const putContext = (sid: string, context: ProjectContext, version?: string) => contextRequest<{projectContext: ProjectContext; warnings: string[]}>(versionQuery(`/context/${encodeURIComponent(sid)}`, version), "PUT", context);
export const patchSession = (sid: string, patch: {step?: string; drafts?: Record<string, unknown>}, version?: string) => contextRequest(versionQuery(`/session/${encodeURIComponent(sid)}`, version), "PATCH", patch);
export const suggestCategory = (bk: string, oneLiner: string) => contextRequest<ProjectContext["productCategory"]>("/context/category-suggest", "POST", {bk, oneLiner});
export const contextSessions = () => contextRequest<{sessions: SessionInfo[]}>("/sessions");
