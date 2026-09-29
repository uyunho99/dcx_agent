export type Axis = 'physical' | 'psychological' | 'behavioral';
export type Destination = { axis: Axis; sub: string };
export type Rejection = { tags: string[]; note: string; to?: Destination };
export type Keyword = Destination & { id: string; kw: string; round: number; origin: 'llm' | 'manual' | 'suggested'; status: 'pending' | 'approved' | 'rejected'; reject?: Rejection | null; badges: string[]; volume?: { monthly?: number | null; source?: string; error?: unknown } | null };
export type Decision = { id: string; status: 'approved' | 'rejected'; reject?: Rejection | null };
export type Job = { status: 'running' | 'done' | 'failed'; round: number; gen: number; startedAt: string; error?: { kind: string; message?: string } | null };
export type Round = { round: number; gen: number; job: Job; committed: boolean; keywords: Keyword[]; below_min?: { got: number; min: number } | null };
export type Coverage = { status?: string; m1?: number | null; m2?: (number | null)[]; m6?: number | null; m7?: number | null; missing_top?: [string, number][]; humanQueries?: unknown[] };
export type KeywordState = { keywords: Keyword[]; keywordRounds: Record<string, Round>; coverage: Coverage; feedback_md: string };
export type Draft = { round: number; gen: number; decisions: Decision[]; groups?: Destination[] };
export class KeywordApiError extends Error {
  constructor(message: string, public kind?: string, public duplicateOf?: string, public status?: number) { super(message); }
}
const API = process.env.NEXT_PUBLIC_API_URL || '';
async function request<T>(sid: string, path = '', method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${API}/keywords/${encodeURIComponent(sid)}${path}`, { method, headers: { 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok || data.status === 'error') throw new KeywordApiError(data.error?.message || '요청에 실패했습니다. 다시 시도하세요.', data.error?.kind, data.duplicateOf, response.status);
  return data;
}
export const getKeywords = (sid: string) => request<KeywordState>(sid);
export const startRound = (sid: string, n: number) => request<Job>(sid, `/rounds/${n}`, 'POST');
export const regenerateRound = (sid: string, n: number) => request<Job>(sid, `/rounds/${n}?regenerate=true`, 'POST');
export const getRound = (sid: string, n: number) => request<Job & Omit<Round, 'job'>>(sid, `/rounds/${n}`);
export const commitRound = (sid: string, n: number, gen: number, decisions: Decision[]) => request(sid, `/rounds/${n}/commit`, 'POST', { gen, decisions });
export type ReviewEvent = { round: number; type: 'direction' | 'approve' | 'reject' | 'move' | 'unreject'; kwId?: string; tags?: string[]; note?: string; text?: string; to?: Destination };
export const postEvent = (sid: string, event: ReviewEvent) => request<{ feedback_md: string }>(sid, '/events', 'POST', event);
export const addKeyword = (sid: string, kw: string, to: Destination, origin: 'manual' | 'suggested') => request<Keyword>(sid, '/manual', 'POST', { kw, ...to, origin });
export const suggestWords = (sid: string, to: Destination) => request<{ words: { word: string; type: string }[] }>(sid, '/suggest-words', 'POST', to);
export const getCoverage = (sid: string) => request<Coverage>(sid, '/coverage', 'POST');
