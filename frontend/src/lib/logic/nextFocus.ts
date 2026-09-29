/** IDs are opaque; rows come from rendered chip positions, never from ID parsing. */
export function nextFocus(grid: readonly (readonly string[])[], current: string, key: string): string | null {
  const rows = grid.filter(row => row.length); const flat = rows.flat();
  if (!flat.length) return null;
  const index = flat.indexOf(current);
  if (index < 0 || key === 'Home') return flat[0];
  if (key === 'End') return flat[flat.length - 1];
  if (key === 'ArrowLeft' || key === 'ArrowRight') return flat[Math.max(0, Math.min(flat.length - 1, index + (key === 'ArrowLeft' ? -1 : 1)))];
  const row = rows.findIndex(r => r.includes(current)); const col = rows[row].indexOf(current);
  if (key === 'ArrowUp' || key === 'ArrowDown') {
    const dest = rows[Math.max(0, Math.min(rows.length - 1, row + (key === 'ArrowUp' ? -1 : 1)))];
    return dest[Math.min(col, dest.length - 1)];
  }
  return current;
}
