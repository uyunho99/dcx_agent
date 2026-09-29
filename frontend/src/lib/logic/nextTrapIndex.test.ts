import { describe, expect, it } from "vitest";
import { nextTrapIndex } from "./nextTrapIndex";

describe("nextTrapIndex", () => {
  it("wraps Tab and Shift+Tab at the dialog boundaries", () => {
    expect(nextTrapIndex(3, 2, false)).toBe(0);
    expect(nextTrapIndex(3, 0, true)).toBe(2);
    expect(nextTrapIndex(3, 0, false)).toBe(1);
    expect(nextTrapIndex(3, 2, true)).toBe(1);
  });
  it("enters from the dialog or outside focus", () => {
    expect(nextTrapIndex(3, -1, false)).toBe(0);
    expect(nextTrapIndex(3, -1, true)).toBe(2);
  });
  it("handles no controls and a single control", () => {
    expect(nextTrapIndex(0, -1, false)).toBe(-1);
    expect(nextTrapIndex(0, -1, true)).toBe(-1);
    expect(nextTrapIndex(1, 0, false)).toBe(0);
    expect(nextTrapIndex(1, 0, true)).toBe(0);
  });
});
