import { expect, it } from 'vitest';
import { roundKeywords } from './roundKeywords';

const all = [
  { id: 'r3-first', round: 3 },
  { id: 'r1-first', round: 1 },
  { id: 'r3-second', round: 3 },
  { id: 'r1-second', round: 1 },
];

it('keeps only the selected round', () => {
  expect(roundKeywords(all, 1, false)).toEqual([all[1], all[3]]);
  expect(roundKeywords(all, 3, false)).toEqual([all[0], all[2]]);
  expect(roundKeywords(all, 2, false)).toEqual([]);
  expect(roundKeywords([], 1, false)).toEqual([]);
});

it('returns everything on the final view', () => {
  for (const round of [1, 2, 3, 4]) {
    expect(roundKeywords(all, round, true)).toBe(all);
    expect(roundKeywords(all, round, true).map(k => k.id)).toEqual([
      'r3-first', 'r1-first', 'r3-second', 'r1-second',
    ]);
  }
  const empty: typeof all = [];
  expect(roundKeywords(empty, 4, true)).toBe(empty);
});
