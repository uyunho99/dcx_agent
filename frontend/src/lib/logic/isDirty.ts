/** Compare JSON-like form values without depending on property insertion order. */
export function isDirty(saved: unknown, current: unknown): boolean {
  if (Object.is(saved, current)) return false;
  if (!saved || !current || typeof saved !== "object" || typeof current !== "object") return true;
  if (Array.isArray(saved) !== Array.isArray(current)) return true;
  if (Array.isArray(saved) && Array.isArray(current)) {
    return saved.length !== current.length || saved.some((value, index) => isDirty(value, current[index]));
  }
  const a = saved as Record<string, unknown>, b = current as Record<string, unknown>;
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].some(key => isDirty(a[key], b[key]));
}
