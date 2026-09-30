import type { ModelMetadata, TrainingStatus } from '../../lib/types';

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
export function number(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}
export function percent(value: unknown): string {
  const n = number(value);
  return n === undefined ? '확인 불가' : `${(n * 100).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`;
}
export function trainingState(status: TrainingStatus) {
  const workers = status.workers ?? [];
  const failed = workers.find(w => ['failed', 'interrupted', 'cancelled', 'paused'].includes(w.state));
  const busy = workers.some(w => w.state === 'running') || (!failed && status.training.inferStatus === 'running');
  return { busy, ready: !busy && !failed && !!status.training.modelId && status.training.inferStatus === 'done', error: failed ? failed.error || '작업이 멈췄습니다. 다시 학습하거나 모델 없이 내보내세요.' : '' };
}
export function mlpDifference(metrics: Record<string, unknown>): number | undefined {
  if (!Array.isArray(metrics.members) || metrics.members.length !== 4) return undefined;
  const values = metrics.members.map(m => number(record(m).grade_accuracy));
  if (values.some(v => v === undefined)) return undefined;
  return ((values[0]! + values[1]! + values[2]!) / 3 - values[3]!) * 100;
}
export function ensembleModels(models: ModelMetadata[]): ModelMetadata[] {
  return models.filter(m => m.kind === 'ensemble');
}

export async function exportAndAdvance(write: () => Promise<unknown>, patch: () => Promise<unknown>, navigate: () => void) {
  await write();
  await patch();
  navigate();
}
