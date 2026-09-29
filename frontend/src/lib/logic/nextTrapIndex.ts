/** -1 means focus should remain on the dialog when no controls are available. */
export function nextTrapIndex(count: number, current: number, shift: boolean): number {
  if (count <= 0) return -1;
  if (current < 0 || current >= count) return shift ? count - 1 : 0;
  return (current + (shift ? -1 : 1) + count) % count;
}
