import { describe, expect, it } from "vitest";
import { isDirty } from "./isDirty";

describe("isDirty", () => {
  it("ignores object key order recursively", () => {
    expect(isDirty({a: 1, b: {x: 2, y: 3}}, {b: {y: 3, x: 2}, a: 1})).toBe(false);
  });
  it("treats undefined and missing keys alike", () => {
    expect(isDirty({a: {b: undefined}}, {a: {}})).toBe(false);
    expect(isDirty(undefined, undefined)).toBe(false);
  });
  it("detects nested edits, array order and removals", () => {
    expect(isDirty({a: [1, 2]}, {a: [2, 1]})).toBe(true);
    expect(isDirty({a: [1]}, {a: []})).toBe(true);
    expect(isDirty({a: {b: 1}}, {a: {b: 2}})).toBe(true);
  });
  it("distinguishes null, empty containers and primitive types", () => {
    expect(isDirty(null, undefined)).toBe(true);
    expect(isDirty([], {})).toBe(true);
    expect(isDirty(1, "1")).toBe(true);
    expect(isDirty(null, null)).toBe(false);
  });
});
