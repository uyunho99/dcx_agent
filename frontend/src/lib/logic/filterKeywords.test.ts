import { describe, expect, it } from 'vitest';
import { filterKeywords } from './filterKeywords';
const kws = [
  { id: 'opaque/a', kw: '바람 소리', badges: ['llm_only'], status: 'pending', origin: 'llm' },
  { id: 'opaque/b', kw: '새벽', badges: ['low_volume'], status: 'approved', origin: 'llm' },
  { id: 'opaque/c', kw: '소음', badges: ['misclassified_suspect'], status: 'pending', origin: 'llm' },
  { id: 'opaque/d', kw: 'Manual', badges: [], status: 'rejected', origin: 'manual', volume: { source: 'unconnected' } },
];
describe('filterKeywords', () => {
  it('defaults to the union of review badges without duplicates', () => expect(filterKeywords(kws).map(k => k.id)).toEqual(['opaque/a', 'opaque/b', 'opaque/c']));
  it('combines case-insensitive substring search with filter', () => expect(filterKeywords(kws, '수동', 'MAN')).toEqual([kws[3]]));
  it('supports every badge/status filter', () => {
    for (const [filter, index] of [['LLM 단독', 0], ['검색량 적음', 1], ['미연결', 3], ['거절됨', 3]] as const) expect(filterKeywords(kws, filter)).toEqual([kws[index]]);
    expect(filterKeywords(kws, '전체')).toHaveLength(4);
    expect(filterKeywords(kws, '전체', '없는말')).toEqual([]);
  });
});
