/** Exclusive end; measured row heights include the optional detail row. */
export function crawlWindow(heights: number[], scrollTop: number, viewport: number, overscan = 5) {
  if (heights.length <= 300) return {start:0, end:heights.length, before:0, after:0};
  const offsets = [0];
  heights.forEach(h => offsets.push(offsets[offsets.length-1] + Math.max(1, h)));
  const total = offsets[offsets.length-1];
  const top = Math.max(0, Math.min(scrollTop, total - Math.max(1, viewport)));
  let first = 0; while (first < heights.length - 1 && offsets[first+1] <= top) first++;
  let last = first + 1; while (last < heights.length && offsets[last] < top + viewport) last++;
  const start = Math.max(0, first - overscan), end = Math.min(heights.length, last + overscan);
  return {start, end, before:offsets[start], after:total-offsets[end]};
}
