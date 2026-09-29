type RoundState = { status?: 'running' | 'done' | 'failed'; committed?: boolean; needsRegeneration?: boolean };
const regenerable = (state: RoundState) => state.status !== 'running' && ((state.status === 'done' && !state.committed) || !!state.needsRegeneration);
export const directionRound = (round: number) => Math.min(round + 1, 4);
export function roundUi(state: RoundState & { round: number; nextRound?: RoundState; gen?: number; jobGen?: number; dirty?: boolean }) {
  const running = state.status === 'running';
  const canEdit = !running && state.status !== 'failed' && state.gen === state.jobGen;
  const committed = state.status === 'done' && !!state.committed;
  return { canStart: !running && (state.status === undefined || state.status === 'failed' || (state.round === 4 && committed)),
    showRegenerate: regenerable(state), canRegenerate: regenerable(state) && !state.dirty,
    canCommit: canEdit && state.status === 'done' && !state.committed, canNext: committed && (!state.nextRound || regenerable(state.nextRound)),
    canEdit, final: state.round === 4 && committed };
}
