import type { EvidenceContextState, EvidenceContextStatus, EvidenceLocation } from '../../lib/types';

const rowBadges = {
  queued: '대기', running: '진행 중', done: '완료', failed: '실패', skipped: '건너뜀',
} as const;

export function rowBadge(status: EvidenceContextState) {
  return rowBadges[status];
}

export function canBuildPersona(status: { contexts: Pick<EvidenceContextStatus, 'status'>[] }): boolean {
  return status.contexts.every(context => context.status === 'done' || context.status === 'skipped');
}

export function locationLabel({ field, idx }: EvidenceLocation): string {
  if (field === 'title') return '제목';
  if (field === 'body') return '본문';
  return `댓글 ${(idx ?? 0) + 1}`;
}

export type EvidenceHighlightSegment = { text: string; mark: boolean };

export function highlight(text: string, start: number | null, end: number | null): EvidenceHighlightSegment[] {
  if (start === null || end === null || !Number.isInteger(start) || !Number.isInteger(end)
    || start < 0 || end > text.length || start >= end) return [{ text, mark: false }];
  const segments: EvidenceHighlightSegment[] = [];
  if (start > 0) segments.push({ text: text.slice(0, start), mark: false });
  segments.push({ text: text.slice(start, end), mark: true });
  if (end < text.length) segments.push({ text: text.slice(end), mark: false });
  return segments;
}

export function excludedMessage(n: number): string {
  return `${n}건이 Known Insight와 같아 빠졌습니다`;
}
