import { expect, it } from 'vitest';
import { pickNowCard } from './nowCard';
const base = { started: true, progress: {}, definitionCheck: { needed: false, reason: null }, queue: { total: 0, estimatedSeconds: 0 }, now: { state: 'done' } };
it('offers mode choice and a one-line estimate before starting', () => {
 const card = pickNowCard({ ...base, started: false });
 expect(card.kind).toBe('before_start'); expect(card.action?.label).toBe('라벨링 시작'); expect(card.body).toContain('방식'); expect(card.body).toContain('예상');
});
it('prioritizes a stopped worker over definition, queue and audit', () => {
 expect(pickNowCard({ ...base, progress: { jev: { state: 'paused', pending: 1, reason: '잔액 부족' } }, definitionCheck: { needed: true, reason: '점검' }, queue: { total: 214, estimatedSeconds: 2140 }, now: { state: 'audit' } }).kind).toBe('paused');
});
it('prioritizes definition check over queue', () => expect(pickNowCard({ ...base, definitionCheck: { needed: true, reason: '점검' }, queue: { total: 214, estimatedSeconds: 2140 } }).kind).toBe('definition_check'));
it('prioritizes queue over audit and includes estimate', () => { const card = pickNowCard({ ...base, queue: { total: 214, estimatedSeconds: 2140 }, now: { state: 'audit' } }); expect(card.kind).toBe('review'); expect(card.title).toContain('214'); expect(card.body).toContain('36분'); });
it('offers waiting audit before running', () => expect(pickNowCard({ ...base, now: { state: 'audit' }, progress: { gpt: { state: 'running', pending: 10 } } }).kind).toBe('audit'));
it('has no action while judging', () => { const card = pickNowCard({ ...base, progress: { gpt: { state: 'running', pending: 10 } } }); expect(card.kind).toBe('running'); expect(card.action).toBeUndefined(); });
it('offers training when all done', () => expect(pickNowCard(base).kind).toBe('done'));
