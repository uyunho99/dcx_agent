function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

/** Last completed stage (inclusive); zero means no completed pipeline stage. */
export function completedThrough(session?: Record<string, unknown> | null): number {
  if (!session) return 0;
  if (Object.keys(record(session.clusters)).length > 0) return 6;
  const exportRef = record(session.training).exportRef;
  if (typeof exportRef === 'string' && exportRef.trim()) return 5;
  if (record(session.labeling).status === 'done') return 4;
  if (record(session.prep).status === 'done') return 3;
  const crawl = record(session.crawl);
  if (session.step === 'crawl-done' || (crawl.kind === 'detail' && crawl.status === 'done')) return 2;
  if (record(record(session.keywordRounds)['4']).committed === true) return 1;
  return 0;
}
