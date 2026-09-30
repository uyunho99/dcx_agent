export function channelBars(perSource: Record<string, {listed: number; filtered: number}>) {
  const counts = Object.entries(perSource).map(([source, cell]) => ({source, count: Number.isFinite(cell.listed - cell.filtered) ? Math.max(0, cell.listed - cell.filtered) : 0}));
  const total = counts.reduce((sum, cell) => sum + cell.count, 0);
  return counts.map(cell => ({...cell, ratio: total ? cell.count / total : 0, dashed: cell.count === 0}));
}
