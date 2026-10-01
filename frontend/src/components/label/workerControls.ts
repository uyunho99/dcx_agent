export type WorkerAction = 'pause' | 'resume' | 'stop';
export function controlTarget(name: string, mode: 'llm' | 'model'): 'jev' | 'gpt' | 'infer' | undefined {
  if (name === 'infer' && mode === 'model') return 'infer';
  if (name === 'jev' || name === 'gpt') return name;
  return undefined;
}
export function workerActions(state: string): WorkerAction[] {
  if (state === 'running') return ['pause', 'stop'];
  if (state === 'paused') return ['resume', 'stop'];
  if (['failed', 'interrupted', 'cancelled'].includes(state)) return ['resume'];
  return [];
}
