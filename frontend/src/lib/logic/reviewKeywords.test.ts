import { expect, it } from 'vitest';
import type { Keyword, Round } from '../api/keywords';
import { reviewKeywords } from './reviewKeywords';

it('excludes stale round keywords from review and counts, including duplicate IDs', () => {
  const old: Keyword = { id: 'old', kw: '이전', round: 1, origin: 'llm', status: 'rejected', axis: 'physical', sub: 'test', badges: [] };
  const saved: Keyword = { ...old, id: 'saved', status: 'approved' };
  for (const status of ['running', 'failed', 'done'] as const) {
    const round: Round = { round: 1, gen: 1, job: { round: 1, gen: 2, status, startedAt: '' }, committed: false, keywords: [old] };
    expect(reviewKeywords({ keywordRounds: { '1': round }, keywords: [saved, old] })).toEqual([saved]);
    if (status !== 'done') expect(reviewKeywords({ keywordRounds: { '1': { ...round, gen: 2 } }, keywords: [saved] })).toEqual([saved]);
  }
  const round: Round = { round: 1, gen: 2, job: { round: 1, gen: 2, status: 'done', startedAt: '' }, committed: false, keywords: [old] };
  expect(reviewKeywords({ keywordRounds: { '1': round }, keywords: [saved] })).toEqual([old, saved]);
});
