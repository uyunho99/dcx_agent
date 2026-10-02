import { expect, it } from 'vitest';
import { roundKeywords, roundTag } from './roundKeywords';

const all = [
  { id: 'r1-approved', round: 1, status: 'approved' },
  { id: 'r1-rejected', round: 1, status: 'rejected' },
  { id: 'r3-pending', round: 3, status: 'pending' },
  { id: 'r3-rejected', round: 3, status: 'rejected' },
  { id: 'r4-approved', round: 4, status: 'approved' },
];

it('keeps the selected round and earlier approved keywords', () => {
  expect(roundKeywords(all, 3, false)).toEqual([all[0], all[2], all[3]]);
  expect(roundKeywords(all, 1, false)).toEqual([all[0], all[1]]);
  expect(roundKeywords([], 1, false)).toEqual([]);
});

it('returns everything on the final view', () => {
  for (const round of [1, 2, 3, 4]) {
    expect(roundKeywords(all, round, true)).toBe(all);
    expect(roundKeywords(all, round, true).map(k => k.id)).toEqual([
      'r1-approved', 'r1-rejected', 'r3-pending', 'r3-rejected', 'r4-approved',
    ]);
  }
  const empty: typeof all = [];
  expect(roundKeywords(empty, 4, true)).toBe(empty);
});

it('tags only earlier-round keywords', () => {
  expect(roundTag(1, 3)).toBe('R1');
  expect(roundTag(3, 3)).toBeUndefined();
  expect(roundTag(1, undefined)).toBeUndefined();
  expect(roundTag(4, 3)).toBe('R4');
});
