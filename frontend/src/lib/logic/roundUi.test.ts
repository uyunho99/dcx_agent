import { expect, it } from 'vitest';
import { roundUi, directionRound, nextRound, prevRound, followingRound, LOCKED_ROUNDS } from './roundUi';
it('has no following round after R4 while skipping locked R2', () => {
  expect(followingRound(1)).toBe(3);
  expect(followingRound(3)).toBe(4);
  expect(followingRound(4)).toBeUndefined();
  expect(followingRound(5)).toBeUndefined();
});
it('allows committed R4 to advance when its own state is not used as the next round', () => {
  const current = { round: 4, status: 'done' as const, committed: true };
  expect(roundUi({ ...current, nextRound: undefined }).canNext).toBe(true);
  expect(roundUi({ ...current, nextRound: current }).canNext).toBe(false);

  const rounds = { '4': current } as Record<string, typeof current>;
  const following = followingRound(current.round);
  const nextState = following === undefined ? undefined : rounds[String(following)];
  const ui = roundUi({ ...current, nextRound: nextState });
  expect(ui.canNext).toBe(true);
  expect(current.round === 4 || !nextState || ui.canNext).toBe(true);
});
it('skips locked R2 when advancing', () => {
  expect(nextRound(1)).toBe(3);
  expect(nextRound(3)).toBe(4);
  expect(nextRound(4)).toBe(4);
  expect(prevRound(3)).toBe(1);
  expect(prevRound(4)).toBe(3);
  expect(prevRound(1)).toBe(1);
  expect(directionRound(1)).toBe(3);
  expect(directionRound(4)).toBe(4);
  expect(LOCKED_ROUNDS).toEqual([2]);
});
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
it('requires explicit regeneration permission for committed rounds', () => {
  for (const round of [1, 2, 3, 4]) {
    expect(roundUi({ round, status: 'done', committed: false }).canRegenerate).toBe(true);
    expect(roundUi({ round, status: 'done', committed: true }).canRegenerate).toBe(false);
    for (const status of [undefined, 'running', 'failed'] as const) {
      expect(roundUi({ round, status }).canRegenerate).toBe(false);
    }
  }
});
it('locks failed and mismatched generations while keeping retries available', () => {
  expect(roundUi({ round: 1, status: 'failed', gen: 1, jobGen: 2 })).toMatchObject({ canEdit: false, canCommit: false, canStart: true });
  expect(roundUi({ round: 1, status: 'done', gen: 1, jobGen: 2 })).toMatchObject({ canEdit: false, canCommit: false });
  expect(roundUi({ round: 1, status: 'done', gen: 2, jobGen: 2 }).canEdit).toBe(true);
});
it('requires saving dirty decisions before regeneration', () => {
  expect(roundUi({ round: 1, status: 'done', dirty: true }).canRegenerate).toBe(false);
  expect(roundUi({ round: 1, status: 'done', dirty: false }).canRegenerate).toBe(true);
});

it('permits restart regeneration and protects existing next rounds',()=>{
 expect(roundUi({round:1,status:'done',committed:true,needsRegeneration:true}).canRegenerate).toBe(true);
 expect(roundUi({round:1,status:'done',committed:true,nextRound:{status:'done',committed:true}}).canNext).toBe(false);
 expect(roundUi({round:1,status:'done',committed:true,nextRound:{status:'done',committed:true,needsRegeneration:true}}).canNext).toBe(true);
 expect(roundUi({round:1,status:'done',committed:true,nextRound:{status:'done',committed:false}}).canNext).toBe(true);
 expect(roundUi({round:1,status:'done',committed:true,nextRound:{status:'running'}}).canNext).toBe(false);
});
it('tags directions saved at commit with the upcoming generation',()=>{
 expect([1,2,3,4].map(directionRound)).toEqual([3,3,4,4]);
});
