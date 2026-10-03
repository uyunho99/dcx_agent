import { expect, it } from 'vitest';
import { formatRate, GPT_ONLY_BODY, GPT_ONLY_TITLE, isGptOnly } from './labelerMode';

it('recognizes GPT-only mode while retaining cross mode for older overviews', () => {
 expect(isGptOnly({labelerMode:'gpt_only'})).toBe(true);
 expect(isGptOnly({labelerMode:'cross'})).toBe(false);
 expect(isGptOnly({})).toBe(false);
});
it('renders unavailable rates as a dash and preserves percentage precision', () => {
 expect(formatRate(null)).toBe('—');
 expect(formatRate(undefined)).toBe('—');
 expect(formatRate(0)).toBe('0.0%');
 expect(formatRate(.12345)).toBe('12.3%');
 expect(formatRate(1)).toBe('100.0%');
});
it('explains adoption, random audits, and how to start cross labeling', () => {
 expect(GPT_ONLY_TITLE).toBe('Jev 미연결 · GPT 단독 판정');
 expect(GPT_ONLY_BODY).toBe('등급 불일치 검수 없이 GPT 판정을 그대로 채택합니다. 오류는 무작위 감사로 확인합니다. Jev를 연결한 뒤 새 버전에서 시작하면 교차 판정합니다.');
});
