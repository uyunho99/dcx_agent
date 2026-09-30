import type { Overview, QueueItem, ReviewMode } from '@/lib/types';

const reasonLabels = {
  labeler_failed: '판정 실패',
  grade_mismatch: '두 라벨러 등급 불일치',
  model_uncertain: '모델 불확실',
  model_disagree: '모델 멤버 불일치',
};

export function queueReasonLabel(reason: QueueItem['reason'], mode: ReviewMode = 'escalate'): string {
  return reason ? reasonLabels[reason] : mode === 'reissue' ? '이전 감사 다시 판정' : '감사 판정';
}

export function queueReasonSummary(mode: Overview['mode'], counts: Overview['queue']['byReason']): string {
  return mode === 'model'
    ? `${reasonLabels.model_uncertain} ${counts.model_uncertain ?? 0}건 · ${reasonLabels.model_disagree} ${counts.model_disagree ?? 0}건`
    : `등급 불일치 ${counts.grade_mismatch ?? 0}건 · ${reasonLabels.labeler_failed} ${counts.labeler_failed ?? 0}건`;
}
