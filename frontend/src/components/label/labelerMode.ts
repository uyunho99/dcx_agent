import type { Overview } from '@/lib/api/label';

export const GPT_ONLY_TITLE = 'Jev 미연결 · GPT 단독 판정';
export const GPT_ONLY_BODY = '등급 불일치 검수 없이 GPT 판정을 그대로 채택합니다. 오류는 무작위 감사로 확인합니다. Jev를 연결한 뒤 새 버전에서 시작하면 교차 판정합니다.';

export function isGptOnly(o: Pick<Overview, 'labelerMode'>): boolean {
 return o.labelerMode === 'gpt_only';
}
export function formatRate(value: number | null | undefined): string {
 return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}
export function labelerView(o: Pick<Overview, 'labelerMode' | 'progress' | 'mode'>, mode = o.mode) {
 const showNotice = mode === 'llm' && isGptOnly(o);
 return {showNotice, workers:Object.entries(o.progress).filter(([name]) => !showNotice || name === 'gpt')};
}
