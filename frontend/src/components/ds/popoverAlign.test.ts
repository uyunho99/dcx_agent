import { describe, expect, it } from "vitest";
import { popoverAlign } from "./popoverAlign";

describe("popoverAlign", () => {
  it("keeps end when there is enough room", () => {
    expect(popoverAlign(100, 400, 0, 800)).toBe("end");
  });

  it("uses start when the panel overflows the left boundary", () => {
    expect(popoverAlign(-200, 100, 0, 800)).toBe("start");
  });

  it("uses start when both alignments overflow but start overflows less", () => {
    expect(popoverAlign(-200, 100, 0, 350)).toBe("start");
  });

  it("keeps end when both alignments overflow but end overflows less", () => {
    expect(popoverAlign(-20, 280, 0, 350)).toBe("end");
  });

  it("keeps end on equal overflow", () => {
    expect(popoverAlign(-150, 150, 0, 300)).toBe("end");
  });

  it("respects the margin, including its exact edge", () => {
    expect(popoverAlign(8, 308, 0, 800)).toBe("end");
    expect(popoverAlign(7, 307, 0, 800)).toBe("start");
    expect(popoverAlign(7, 307, 0, 800, 0)).toBe("end");
    expect(popoverAlign(115, 415, 100, 900, 16)).toBe("start");
  });

  it("accounts for the measured start edge of a nonzero-width trigger", () => {
    expect(popoverAlign(-20, 280, 0, 350, 8, 40)).toBe("start");
  });
});
