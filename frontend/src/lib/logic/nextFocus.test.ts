import { expect, it } from 'vitest';
import { nextFocus } from './nextFocus';
const grid = [['opaque/a', 'b', 'c'], ['d', 'e'], ['f']];
it('moves across rows horizontally and clamps at group boundaries', () => {
  expect(nextFocus(grid, 'c', 'ArrowRight')).toBe('d');
  expect(nextFocus(grid, 'd', 'ArrowLeft')).toBe('c');
  expect(nextFocus(grid, 'opaque/a', 'ArrowLeft')).toBe('opaque/a');
});
it('moves vertically with ragged rows and Home/End', () => {
  expect(nextFocus(grid, 'c', 'ArrowDown')).toBe('e');
  expect(nextFocus(grid, 'e', 'ArrowUp')).toBe('b');
  expect(nextFocus(grid, 'e', 'Home')).toBe('opaque/a');
  expect(nextFocus(grid, 'e', 'End')).toBe('f');
});
it('preserves Tab and handles missing/empty focus', () => {
  expect(nextFocus(grid, 'b', 'Tab')).toBe('b');
  expect(nextFocus(grid, 'missing', 'ArrowRight')).toBe('opaque/a');
  expect(nextFocus([], 'missing', 'Home')).toBeNull();
});
