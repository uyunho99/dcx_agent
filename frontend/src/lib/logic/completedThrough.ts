function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

/** Last completed stage (inclusive); zero means no completed pipeline stage. */
export function completedThrough(session?: Record<string, unknown> | null): number {
  if (!session) return 0;
  const completion = record(session.completion);
  const done = (key: string, fallback: boolean) =>
    typeof completion[key] === 'boolean' ? completion[key] : fallback;
  if (done('insightDone', false)) return 9;
  if (done('personaDone', false)) return 8;
  const legacyClustersDone = done('clustersDone', Object.keys(record(session.clusters)).length > 0);
  if (done('evidenceDone', false)) return 7;
  if (done('segmentDone', legacyClustersDone)) return 6;
  const exportRef = record(session.training).exportRef;
  if (done('exportDone', typeof exportRef === 'string' && !!exportRef.trim())) return 5;
  if (done('labelingDone', record(session.labeling).status === 'done')) return 4;
  if (done('prepDone', record(session.prep).status === 'done')) return 3;
  const crawl = record(session.crawl);
  if (done('crawlDone', session.step === 'crawl-done' || (crawl.kind === 'detail' && crawl.status === 'done'))) return 2;
  if (record(record(session.keywordRounds)['4']).committed === true) return 1;
  return 0;
}
