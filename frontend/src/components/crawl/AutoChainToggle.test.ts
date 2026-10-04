import { describe, expect, it } from 'vitest';
import { autoChainLabel } from './AutoChainToggle';

describe('autoChainLabel', () => {
  it('describes started and failed automatic steps', () => {
    expect(autoChainLabel(undefined)).toBe('');
    expect(autoChainLabel({ stage: 'prep', state: 'running' })).toBe('자동으로 전처리를 시작했습니다.');
    expect(autoChainLabel({ stage: 'labeling', state: 'failed', error: '전처리를 먼저 완료하세요.' })).toBe('자동 라벨링 시작 실패: 전처리를 먼저 완료하세요.');
  });
});
