import { expect, it, vi } from 'vitest';
vi.mock('@/components/ds', () => ({}));
vi.mock('@/components/known/SourceCard', () => ({}));
vi.mock('@/components/DirtyProvider', () => ({}));
import { normalizeChatReply, sourceEmptyMessage } from './ChatPanel';
import { stepIndex } from './StepBar';
import { activityLabel } from './SessionList';
it('preserves legacy replies and only admits sources with document IDs', () => {
 expect(normalizeChatReply('hello')).toEqual({answer:'hello'});
 expect(normalizeChatReply({answer:'a',sources:[{doc_id:'d',text:'e'}, {},null],reason:'all_known'})).toEqual({answer:'a',sources:[{doc_id:'d',text:'e'}],reason:'all_known'});
 expect(() => normalizeChatReply({status:'error',answer:'secret'})).toThrow();
});
it('distinguishes all excluded from unavailable search', () => {
 expect(sourceEmptyMessage('all_known',true)).toBe("이미 아는 이야기를 빼니 남는 원문이 없습니다. '새 발견 찾기'를 끄면 모두 보입니다.");
 expect(sourceEmptyMessage('all_known',false)).not.toContain('이미 아는');
 expect(sourceEmptyMessage('no_vectors',true)).toContain('전처리');
 expect(sourceEmptyMessage('no_labels',true)).toContain('라벨');
 expect(sourceEmptyMessage('embedder_unconnected',true)).toContain('연결');
});
it('recognizes every new stage prefix and preserves old steps', () => {
 for(const step of ['prep-setup','prep-running','prep-done']) expect(stepIndex(step)).toBe(3);
 for(const step of ['label-setup','label-queue','label-audit']) expect(stepIndex(step)).toBe(4);
 for(const step of ['train-setup','train-running','train-export']) expect(stepIndex(step)).toBe(5);
 expect(stepIndex('r3')).toBe(1);expect(stepIndex('unknown')).toBe(0);
});
it('names stage 3–5 activity without calling it collection', () => {
 expect(activityLabel({kind:'label',status:'running',progress:42})).toBe('판정 42%');
 expect(activityLabel({kind:'train',status:'running'})).toBe('학습 중');
 expect(activityLabel({kind:'prep',status:'running',progress:12})).toBe('전처리 12%');
 expect(activityLabel({kind:'classify',status:'running',progress:62})).toBe('분류 62%');
 expect(activityLabel({kind:'label',status:'interrupted'})).toBe('중단됨 · 이어서 진행');
});
it('uses fractional worker progress and server badge wording', () => {
 expect(activityLabel({kind:'judge',status:'running',progress:0.42})).toBe('판정 42%');
 expect(activityLabel({kind:'prep',status:'running',progress:0.12})).toBe('전처리 12%');
 expect(activityLabel({kind:'infer',status:'running',progress:0.62})).toBe('분류 62%');
 expect(activityLabel({kind:'train',status:'running',progress:0.5,label:'학습 중'})).toBe('학습 중');
});

it.each(['paused','blocked','failed','done','idle','running'])('prefers server label for %s', status => {
 expect(activityLabel({kind:'train',status,label:'서버 안내'})).toBe('서버 안내');
});
