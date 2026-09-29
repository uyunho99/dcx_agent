import { contextRequest } from './context';
import type { SessionData, ProjectContext } from '@/lib/types';
import type { KeywordState, Round } from './keywords';
export type Stage = `stage${number}`;
export type VersionEntry = { id: string; parent: string | null; restartFrom: Stage; createdAt: string; note: string; readonly: boolean; collectionId: string | null };
export type VersionList = { activeVersion: string; versions: VersionEntry[] };
export type VersionSession = SessionData & { keywords?: KeywordState['keywords']; stale?: Record<string, string>; parentVersion?: string; version?: string; collectionId?: string };
const base = (sid: string) => `/sessions/${encodeURIComponent(sid)}`;
export const versionPath = (path: string, version?: string) => version ? `${path}${path.includes('?') ? '&' : '?'}version=${encodeURIComponent(version)}` : path;
export const listVersions = (sid: string) => contextRequest<VersionList>(`${base(sid)}/versions`);
// Pydantic VersionRequest.from_v has alias='from'; the wire key is 'from'.
export const createVersion = (sid: string, from_v: string, restartFrom: Stage, note: string) => contextRequest<{version: string}>(`${base(sid)}/versions`, 'POST', { from: from_v, restartFrom, note });
export const getVersionSession = (sid: string, version?: string) => contextRequest<{data: VersionSession}>(versionPath(`/session/${encodeURIComponent(sid)}`, version));
export const getVersionContext = (sid: string, version?: string) => contextRequest<{projectContext: ProjectContext; draft?: ProjectContext | null}>(versionPath(`/context/${encodeURIComponent(sid)}`, version));
export const getVersionKeywords = (sid: string, version?: string) => contextRequest<KeywordState>(versionPath(`/keywords/${encodeURIComponent(sid)}`, version));
export const getVersionRound = (sid: string, n: number, version?: string) => contextRequest<Round['job'] & Omit<Round, 'job'>>(versionPath(`/keywords/${encodeURIComponent(sid)}/rounds/${n}`, version));
export const compareVersions = <T,>(sid: string, a: string, b: string, stage: Stage) => contextRequest<T>(`${base(sid)}/compare?${new URLSearchParams({a,b,stage})}`);
