import type { Stage } from '../api/versions';

type GateScope = {collectionId?: string | null; snapshot_id?: string | null};
type GateDraft = GateScope & {exclusions: string[]};
export type GateSelection = GateScope & {excluded: string[]; saved: string[]; draft: string[]};
export const sameGateScope = (a: GateScope, b: GateScope) => a.collectionId === b.collectionId && a.snapshot_id === b.snapshot_id;

export function reconcileGateSelection(previous: GateSelection | null, status: GateScope & {gate: {kw: string}[] | null}, saved: string[], draft?: GateDraft | null): GateSelection {
  const rows = new Set(status.gate?.map(row => row.kw) ?? []);
  const prune = (keywords: string[]) => [...new Set(keywords)].filter(keyword => rows.has(keyword));
  const keep = previous && sameGateScope(previous, status);
  const restore = !previous && status.collectionId != null && status.snapshot_id != null && draft && sameGateScope(draft, status);
  const selection = keep ? previous.excluded : restore ? draft.exclusions : saved;
  return {
    collectionId: status.collectionId, snapshot_id: status.snapshot_id,
    excluded: prune(selection), saved: prune(keep ? previous.saved : saved),
    draft: prune(keep ? previous.draft : selection),
  };
}

export const stalePageStage = (stage: Stage, stale?: Record<string, string>): Stage | null => stale?.[stage] ? stage : null;
export const formatCrawlNumber = (value: number) => value.toLocaleString('en-US', {maximumFractionDigits: 1});
export const crawlWorkerRunning = (status: string) => status === 'running' || status === 'stopping';
