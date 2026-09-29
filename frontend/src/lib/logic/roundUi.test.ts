import { expect, it } from 'vitest';
import { roundUi } from './roundUi';
it('allows initial start and disables every mutation during running', () => {
  expect(roundUi({ round: 1 }).canStart).toBe(true);
  expect(roundUi({ round: 2, status: 'running' })).toMatchObject({ canStart: false, canCommit: false, canNext: false, canEdit: false });
});
it('requires commit before advancing through all four rounds', () => {
  for (const round of [1, 2, 3, 4]) {
    expect(roundUi({ round, status: 'done', committed: false })).toMatchObject({ canCommit: true, canNext: false, canStart: false });
    expect(roundUi({ round, status: 'done', committed: true })).toMatchObject({ canCommit: false, canNext: true, final: round === 4 });
  }
});
it('allows failed retries and only R4 additional generation after commit', () => {
  expect(roundUi({ round: 3, status: 'failed' }).canStart).toBe(true);
  expect(roundUi({ round: 3, status: 'done', committed: true }).canStart).toBe(false);
  expect(roundUi({ round: 4, status: 'done', committed: true }).canStart).toBe(true);
});
