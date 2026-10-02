type RoundState = { status?: 'running' | 'done' | 'failed'; committed?: boolean; needsRegeneration?: boolean };
const regenerable = (state: RoundState) => state.status !== 'running' && ((state.status === 'done' && !state.committed) || !!state.needsRegeneration);
export const LOCKED_ROUNDS: readonly number[] = [2];
export function nextRound(round: number): number {
  let next = Math.min(round + 1, 4);
  while (next < 4 && LOCKED_ROUNDS.includes(next)) next += 1;
  return next;
}
export function followingRound(round: number): number | undefined {
  return round >= 4 ? undefined : nextRound(round);
}
export function prevRound(round: number): number {
  let previous = round - 1;
  while (previous >= 1 && LOCKED_ROUNDS.includes(previous)) previous -= 1;
  return previous >= 1 ? previous : round;
}
export const directionRound = (round: number) => nextRound(round);
export function roundUi(state: RoundState & { round: number; nextRound?: RoundState; gen?: number; jobGen?: number; dirty?: boolean }) {
  const running = state.status === 'running';
  const canEdit = !running && state.status !== 'failed' && state.gen === state.jobGen;
  const committed = state.status === 'done' && !!state.committed;
  return { canStart: !running && (state.status === undefined || state.status === 'failed' || (state.round === 4 && committed)),
    showRegenerate: regenerable(state), canRegenerate: regenerable(state) && !state.dirty,
    canCommit: canEdit && state.status === 'done' && !state.committed, canNext: committed && (!state.nextRound || regenerable(state.nextRound)),
    canEdit, final: state.round === 4 && committed };
}
