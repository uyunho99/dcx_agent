import { expect, it } from 'vitest';
import { isMoveShortcut, popoverKeyAction } from './keywordKeys';

it('leaves Enter activation to buttons, including cancel and reason buttons', () => {
  expect(popoverKeyAction('BUTTON', 'Enter')).toBe('native');
  expect(popoverKeyAction('button', 'Enter')).toBe('native');
  expect(popoverKeyAction('INPUT', 'Enter')).toBe('submit');
  expect(popoverKeyAction('SELECT', 'Enter')).toBe('submit');
  expect(popoverKeyAction('INPUT', 'Escape')).toBe('native');
});
it('uses physical M for Korean input but ignores modifiers and composition', () => {
  const event = { code: 'KeyM', key: 'ㅡ', metaKey: false, ctrlKey: false, altKey: false, isComposing: false };
  expect(isMoveShortcut(event)).toBe(true);
  expect(isMoveShortcut({ ...event, key: 'M' })).toBe(true);
  for (const flag of ['metaKey', 'ctrlKey', 'altKey', 'isComposing']) {
    expect(isMoveShortcut({ ...event, [flag]: true })).toBe(false);
  }
  expect(isMoveShortcut({ ...event, code: 'KeyN', key: 'm' })).toBe(false);
});
it('does not submit Enter while Korean IME composition is active', () => {
  expect(popoverKeyAction('INPUT', 'Enter', true)).toBe('native');
  expect(popoverKeyAction('INPUT', 'Enter', false)).toBe('submit');
});
