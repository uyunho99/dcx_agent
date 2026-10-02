import { popoverAlign } from "./popoverAlign";

export function popoverBoundary(panel: HTMLElement): HTMLElement | null {
  for (let ancestor = panel.parentElement; ancestor; ancestor = ancestor.parentElement) {
    const style = getComputedStyle(ancestor);
    if (style.overflowX !== "visible" || style.overflowY !== "visible") return ancestor;
  }
  return null;
}

export function observePopover(panel: HTMLDivElement, trigger: HTMLButtonElement | null) {
  const boundary = popoverBoundary(panel);
  const anchor = trigger ?? panel.parentElement;
  let active = true;
  let frame: number;
  let previousGeometry = "";

  function geometry() {
    // ResizeObserver does not report translations (e.g. sibling reflow or scroll).
    return [anchor, boundary].map(element => {
      const rect = element?.getBoundingClientRect();
      return rect ? [rect.left, rect.top, rect.width, rect.height, element?.clientLeft, element?.clientWidth].join(",") : "viewport";
    }).join(";") + `;${document.documentElement.clientWidth}`;
  }

  function measure() {
    if (!active) return;
    previousGeometry = geometry();
    const boundaryLeft = boundary ? boundary.getBoundingClientRect().left + boundary.clientLeft : 0;
    const boundaryRight = boundary ? boundaryLeft + boundary.clientWidth : document.documentElement.clientWidth;
    // Both trial alignments and the final choice happen before the same paint.
    panel.dataset.align = "end";
    const end = panel.getBoundingClientRect();
    panel.dataset.align = "start";
    const startLeft = panel.getBoundingClientRect().left;
    panel.dataset.align = popoverAlign(end.left, end.right, boundaryLeft, boundaryRight, 8, startLeft);
  }

  function checkPosition() {
    if (!active) return;
    if (geometry() !== previousGeometry) measure();
    frame = requestAnimationFrame(checkPosition);
  }

  // Observer delivery happens before paint. Scheduling another rAF here would
  // leave the old alignment visible for an extra frame after a layout shift.
  const observer = new ResizeObserver(measure);
  if (boundary) observer.observe(boundary);
  if (anchor) observer.observe(anchor);
  observer.observe(panel);
  frame = requestAnimationFrame(checkPosition);
  window.addEventListener("resize", measure);
  return () => {
    active = false;
    cancelAnimationFrame(frame);
    observer.disconnect();
    window.removeEventListener("resize", measure);
    // React owns the initial attribute; retain the last measured value during
    // effect replay/cleanup rather than leaving an open panel without alignment.
  };
}
