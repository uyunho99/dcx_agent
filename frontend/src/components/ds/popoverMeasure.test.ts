import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Popover } from "./Popover";
import { observePopover, popoverBoundary } from "./popoverMeasure";

let frames: Map<number, FrameRequestCallback>;
let nextFrame: number;
let observers: FakeResizeObserver[];
let viewport: EventTarget;
class FakeResizeObserver {
  targets = new Set<Element>();
  constructor(public callback: ResizeObserverCallback) { observers.push(this); }
  observe(target: Element) { this.targets.add(target); }
  disconnect = vi.fn(() => this.targets.clear());
  fire() { this.callback([], this as unknown as ResizeObserver); }
}
function tick() {
  const pending = [...frames.values()];
  frames.clear();
  pending.forEach(callback => callback(0));
}
function fixture() {
  let left = 224;
  let anchorLeft = 339;
  const boundary = {
    parentElement: null, clientLeft: 0, clientWidth: 1216,
    getBoundingClientRect: () => ({ left, right: left + boundary.clientWidth, top: 0, bottom: 800, width: boundary.clientWidth, height: 800 }),
  } as unknown as HTMLElement;
  const anchor = {
    getBoundingClientRect: () => ({ left: anchorLeft, right: anchorLeft + 147, top: 100, bottom: 130, width: 147, height: 30 }),
  } as HTMLButtonElement;
  const panel = {
    parentElement: boundary, dataset: {} as DOMStringMap,
    getBoundingClientRect: vi.fn(() => {
      const x = panel.dataset.align === "start" ? anchorLeft : anchorLeft - 153;
      return { left: x, right: x + 300 };
    }),
    removeAttribute: () => { delete panel.dataset.align; },
  } as unknown as HTMLDivElement;
  return { panel, anchor, boundary, move: (boundaryLeft: number, triggerLeft: number) => { left = boundaryLeft; anchorLeft = triggerLeft; } };
}
beforeEach(() => {
  frames = new Map(); nextFrame = 0; observers = []; viewport = new EventTarget();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.set(++nextFrame, callback); return nextFrame; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("window", viewport);
  vi.stubGlobal("document", { documentElement: { clientWidth: 1440 } });
  vi.stubGlobal("getComputedStyle", () => ({ overflowX: "hidden", overflowY: "auto" }));
});
afterEach(() => vi.unstubAllGlobals());

describe("open popover measurement", () => {
  it("renders an alignment before effects, including contained panels", () => {
    for (const contained of [false, true]) {
      const props = { open: true, contained, label: "Test", triggerLabel: "Open", onOpenChange: () => {}, children: "Panel" };
      expect(renderToStaticMarkup(createElement(Popover, props))).toContain('data-align="end"');
    }
  });
  it("observes the nearest clipping boundary and trigger and corrects a late sidebar shift", () => {
    const f = fixture(); f.move(224, 600);
    const stop = observePopover(f.panel, f.anchor);
    tick(); expect(f.panel.dataset.align).toBe("end");
    expect(observers[0]?.targets.has(f.boundary)).toBe(true);
    expect(observers[0]?.targets.has(f.anchor)).toBe(true);
    f.move(72, 187);
    observers[0].fire();
    // Observer delivery is before paint: do not defer correction another frame.
    expect(f.panel.dataset.align).toBe("start");
    stop();
  });
  it("remeasures position-only changes without ResizeObserver delivery", () => {
    const f = fixture(); f.move(224, 600);
    const stop = observePopover(f.panel, f.anchor);
    tick(); expect(f.panel.dataset.align).toBe("end");
    f.move(72, 187); tick();
    expect(f.panel.dataset.align).toBe("start");
    f.move(72, 600); tick();
    expect(f.panel.dataset.align).toBe("end");
    stop();
  });
  it("keeps alignment through cleanup and ignores queued callbacks after close", () => {
    const f = fixture(); const stop = observePopover(f.panel, f.anchor);
    tick(); expect(f.panel.dataset.align).toBe("start");
    const observer = observers[0]; const queued = [...frames.values()];
    stop();
    expect(f.panel.dataset.align).toBe("start");
    expect(observer.disconnect).toHaveBeenCalledOnce();
    f.panel.getBoundingClientRect = vi.fn();
    observer.fire(); queued.forEach(callback => callback(0)); viewport.dispatchEvent(new Event("resize"));
    expect(f.panel.getBoundingClientRect).not.toHaveBeenCalled();
    expect(frames.size).toBe(0);
  });
  it("remeasures on window resize and skips alignment writes on unchanged frames", () => {
    const f = fixture(); const stop = observePopover(f.panel, f.anchor);
    tick(); vi.mocked(f.panel.getBoundingClientRect).mockClear(); tick();
    expect(f.panel.getBoundingClientRect).not.toHaveBeenCalled();
    f.move(0, 600); viewport.dispatchEvent(new Event("resize")); tick();
    expect(f.panel.dataset.align).toBe("end"); stop();
  });
});


describe("popoverBoundary", () => {
  it("skips visible ancestors and chooses the nearest overflow ancestor", () => {
    const outer = { parentElement: null } as HTMLElement;
    const inner = { parentElement: outer } as HTMLElement;
    const wrapper = { parentElement: inner } as HTMLElement;
    const panel = { parentElement: wrapper } as HTMLElement;
    vi.stubGlobal("getComputedStyle", (element: HTMLElement) => ({ overflowX: element === wrapper ? "visible" : "clip", overflowY: "visible" }));
    expect(popoverBoundary(panel)).toBe(inner);
    vi.stubGlobal("getComputedStyle", () => ({ overflowX: "visible", overflowY: "visible" }));
    expect(popoverBoundary(panel)).toBeNull();
  });
  it("uses the boundary client box including its border offset", () => {
    const f = fixture(); f.move(0, 200);
    Object.defineProperty(f.boundary, "clientLeft", { value: 50 });
    const stop = observePopover(f.panel, f.anchor); tick();
    expect(f.panel.dataset.align).toBe("start"); stop();
  });
  it("uses viewport bounds when no ancestor clips", () => {
    const f = fixture(); f.move(224, 200);
    vi.stubGlobal("getComputedStyle", () => ({ overflowX: "visible", overflowY: "visible" }));
    const stop = observePopover(f.panel, f.anchor); tick();
    expect(f.panel.dataset.align).toBe("end");
    expect(observers[0].targets.has(f.boundary)).toBe(false); stop();
  });
});
