import { expect, it } from 'vitest';
import { josa } from './josa';

it.each([['소음', '을'], ['소음관리', '를'], ['“소음관리”', '를'], ['R0', '을'], ['R1', '을'], ['R2', '를'], ['R3', '을'], ['R4', '를'], ['R5', '를'], ['R6', '을'], ['R7', '을'], ['R8', '을'], ['R9', '를'], ['API', '를'], ['LLM', '을'], ['URL', '을'], ['f', '를'], ['X', '를'], ['Z', '를'], ['', '를'], ['🙂', '를']])('%s + 을/를 = %s', (word, expected) => {
  expect(josa(word, '을/를')).toBe(expected);
});
it('selects subject, topic and conjunction particles', () => {
  expect(josa('소음', '이/가')).toBe('이');
  expect(josa('소음관리', '이/가')).toBe('가');
  expect(josa('R1', '은/는')).toBe('은');
  expect(josa('R2', '은/는')).toBe('는');
  expect(josa('v1', '와/과')).toBe('과');
  expect(josa('v2', '와/과')).toBe('와');
});
