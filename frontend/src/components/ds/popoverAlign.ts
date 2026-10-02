// Without a measured start edge, treat panelRight as a point anchor.
// Popover supplies the actual start edge because triggers have nonzero width.
export function popoverAlign(
  panelLeft: number,
  panelRight: number,
  boundaryLeft: number,
  boundaryRight: number,
  margin = 8,
  startLeft = panelRight,
): "end" | "start" {
  if (panelLeft >= boundaryLeft + margin) return "end";
  const overflow = (left: number, right: number) =>
    Math.max(0, boundaryLeft + margin - left) + Math.max(0, right - boundaryRight + margin);
  const startRight = startLeft + panelRight - panelLeft;
  return overflow(startLeft, startRight) < overflow(panelLeft, panelRight) ? "start" : "end";
}
