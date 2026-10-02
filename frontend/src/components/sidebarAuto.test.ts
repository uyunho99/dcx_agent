import { describe, expect, it, vi } from 'vitest';
import { createSidebarAuto, sidebarCollapsed } from './sidebarAuto';

describe('createSidebarAuto', () => {
  it('notifies when the counter crosses 0 → 1 → 0 and can be reused', () => {
    const onChange = vi.fn();
    const auto = createSidebarAuto(onChange);
    expect(onChange).not.toHaveBeenCalled();
    const release = auto.request();
    expect(onChange.mock.calls).toEqual([[true]]);
    release();
    expect(onChange.mock.calls).toEqual([[true], [false]]);
    auto.request()();
    expect(onChange.mock.calls).toEqual([[true], [false], [true], [false]]);
  });

  it('ignores repeated releases, including after a new request', () => {
    const onChange = vi.fn();
    const auto = createSidebarAuto(onChange);
    const first = auto.request();
    first();
    first();
    const second = auto.request();
    first();
    expect(onChange.mock.calls).toEqual([[true], [false], [true]]);
    second();
    second();
    expect(onChange.mock.calls).toEqual([[true], [false], [true], [false]]);
  });

  it('stays active until both concurrent requests are released', () => {
    const onChange = vi.fn();
    const auto = createSidebarAuto(onChange);
    const first = auto.request();
    const second = auto.request();
    expect(onChange.mock.calls).toEqual([[true]]);
    second();
    second();
    expect(onChange.mock.calls).toEqual([[true]]);
    first();
    expect(onChange.mock.calls).toEqual([[true], [false]]);
  });
});

it.each([
  [false, false, false],
  [false, true, true],
  [true, false, true],
  [true, true, true],
])('sidebarCollapsed(%s, %s) is %s', (user, auto, expected) => {
  expect(sidebarCollapsed(user, auto)).toBe(expected);
});
