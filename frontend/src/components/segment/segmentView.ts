import { displayError } from '../../lib/api/errors';
import type { SegmentContext, SegmentDraft, SegmentErrorKind, SegmentQuality, SegmentStatus } from '../../lib/types';

function allConfirmed(count: string): boolean {
  const match = /^(\d+)\/(\d+)$/.exec(count);
  return !!match && Number(match[2]) > 0 && Number(match[1]) === Number(match[2]);
}
export function layerState(status: SegmentStatus) {
  const { clusters, personas, contexts } = status.confirm;
  const tab = (count: string, locked: boolean, reason: string) => ({locked, reason: locked ? reason : '', progress: `${count} 확정`});
  return {
    clusters: tab(clusters, false, ''),
    personas: tab(personas, !allConfirmed(clusters), '6-A 확정 후'),
    contexts: tab(contexts, !allConfirmed(personas), '6-B 확정 후'),
  };
}

// QualityBadges.tsx currently exports no thresholds. Keep these aligned with params.py.
const COHESION_MIN = .6;
const BOUNDARY_MAX = .15;
const ARI_MIN = { L1: .7, L2: .6 };
export function qualityBadges(quality: SegmentQuality, layer: 'L1' | 'L2' | 'L3' = 'L1') {
  const metrics = [
    {label:'응집', value:quality.cohesion, threshold:COHESION_MIN, note:'분리 검토'},
    {label:'경계', value:quality.boundary, threshold:BOUNDARY_MAX, note:'경계 검토', percent:true},
    {label:'안정', value:quality.ari, threshold:layer === 'L2' ? ARI_MIN.L2 : ARI_MIN.L1, note:'불안정'},
    {label:'NPMI', value:quality.npmi, threshold:-Infinity, note:''},
  ];
  return metrics.flatMap(({label, value, threshold, note, percent}) => {
    if (value == null || !Number.isFinite(value)) return [];
    const warning = percent ? value > threshold : value < threshold;
    return [{text:`${label} ${percent ? `${Math.round(value * 100)}%` : value.toFixed(2)}${warning ? ` · ${note}` : ''}`, warning}];
  });
}
export function bulkConfirmWarning(contexts: Pick<SegmentContext, 'flags'>[]): string | null {
  const count = contexts.filter(context => context.flags.includes('counter_context')).length;
  return count ? `반례 ${count}개 포함` : null;
}
export function canStartEvidence(status: SegmentStatus): {allowed: false; reason: string} {
  // Bundle 2 is unavailable regardless of stage-six completion.
  void status;
  return {allowed:false, reason:'다음 묶음에서 열립니다'};
}
export function currentSegmentDraft<T extends SegmentDraft>(draft: T | null | undefined, run: string | null): T | null {
  return run && draft?.run === run ? draft : null;
}
export function granularityBadge(flags: string[], count: number): string | null {
  return flags.includes('granularity_exceeded') ? `Context가 ${count}개입니다(권장 2~4)` : null;
}
const errorMessages: Record<SegmentErrorKind, string> = {
  locked:'앞 층을 모두 확정한 뒤 진행하세요.',
  confirm_required:'다시 나누면 확정값이 지워집니다. 다시 나누기를 확인하세요.',
  stale_run:'다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.',
  validation:'입력값을 확인하고 다시 시도하세요.',
};
export function segmentErrorMessage(error: unknown): string {
  if (error !== null && typeof error === 'object' && 'error' in error) {
    const detail = error.error;
    if (detail !== null && typeof detail === 'object') {
      const kind = 'kind' in detail && typeof detail.kind === 'string' ? detail.kind : '';
      const fallback = Object.hasOwn(errorMessages, kind) ? errorMessages[kind as SegmentErrorKind] : undefined;
      const message = 'message' in detail && typeof detail.message === 'string' ? detail.message : '';
      return displayError(new Error(message), fallback);
    }
  }
  return displayError(error);
}
