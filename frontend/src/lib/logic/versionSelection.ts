// Once chosen, a version changes only through an explicit user action.
export function resolveVersionSelection(current: string | undefined, meta: { activeVersion: string }) {
  const version = current ?? meta.activeVersion;
  return { version, newerVersion: version !== meta.activeVersion ? meta.activeVersion : undefined };
}
