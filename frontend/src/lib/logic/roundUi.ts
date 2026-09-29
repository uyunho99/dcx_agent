export function roundUi(state: { round: number; status?: 'running' | 'done' | 'failed'; committed?: boolean }) {
  const running = state.status === 'running';
  const committed = state.status === 'done' && !!state.committed;
  return { canStart: !running && (state.status === undefined || state.status === 'failed' || (state.round === 4 && committed)),
    canCommit: state.status === 'done' && !state.committed, canNext: committed,
    canEdit: !running, final: state.round === 4 && committed };
}
