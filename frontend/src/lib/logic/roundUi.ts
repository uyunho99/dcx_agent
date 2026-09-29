export function roundUi(state: { round: number; status?: 'running' | 'done' | 'failed'; committed?: boolean; gen?: number; jobGen?: number; dirty?: boolean }) {
  const running = state.status === 'running';
  const canEdit = !running && state.status !== 'failed' && state.gen === state.jobGen;
  const committed = state.status === 'done' && !!state.committed;
  return { canStart: !running && (state.status === undefined || state.status === 'failed' || (state.round === 4 && committed)),
    canRegenerate: state.status === 'done' && !state.committed && !state.dirty,
    canCommit: canEdit && state.status === 'done' && !state.committed, canNext: committed,
    canEdit, final: state.round === 4 && committed };
}
