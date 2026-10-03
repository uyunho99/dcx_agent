import { expect, it } from 'vitest';
import { queueReasonLabel, queueReasonSummary } from './queueView';

it('labels model escalations without calling them audits', () => {
 expect(queueReasonLabel('model_uncertain')).toBe('모델 불확실');
 expect(queueReasonLabel('model_disagree')).toBe('모델 멤버 불일치');
 expect(queueReasonLabel('grade_mismatch')).toBe('두 라벨러 등급 불일치');
 expect(queueReasonLabel('labeler_failed')).toBe('판정 실패');
 expect(queueReasonLabel(undefined, 'audit')).toBe('감사 판정');
 expect(queueReasonLabel(undefined, 'reissue')).toBe('이전 감사 다시 판정');
});
it('summarizes both model reasons and defaults absent counts to zero', () => {
 expect(queueReasonSummary('model', {model_uncertain:7,model_disagree:3})).toBe('모델 불확실 7건 · 모델 멤버 불일치 3건');
 expect(queueReasonSummary('model', {})).toBe('모델 불확실 0건 · 모델 멤버 불일치 0건');
 expect(queueReasonSummary('llm', {grade_mismatch:2,labeler_failed:1})).toBe('등급 불일치 2건 · 판정 실패 1건');
});

it('uses a fallback for an unknown queue reason', () => {
 const unknown = 'future_reason' as Parameters<typeof queueReasonLabel>[0];
 expect(queueReasonLabel(unknown)).toBe('기타');
 expect(queueReasonLabel(unknown, 'audit')).toBe('기타');
});

import { voteValue } from './queueView';
it('renders unavailable Jev comparison values as dashes while preserving GPT and cross values', () => {
 const votes = {jev:null,gpt:{anchor:true,situation:false,sem:{sense:1 as const,feel:0 as const,think:0 as const,act:0 as const,relate:0 as const,outcome:0 as const}}};
 for(const field of ['anchor','sense','feel','think','act','relate','outcome','situation']) {
  expect(voteValue(votes.jev,field)).toBe('—');
 }
 expect(voteValue(undefined,'anchor')).toBe('—');
 expect(voteValue(votes.gpt,'anchor')).toBe('있음');
 expect(voteValue(votes.gpt,'feel')).toBe('없음');
 expect(voteValue({probs:{anchor:0}},'anchor')).toBe('0.00');
 expect(voteValue({probs:{anchor:.875}},'anchor')).toBe('0.88');
});
