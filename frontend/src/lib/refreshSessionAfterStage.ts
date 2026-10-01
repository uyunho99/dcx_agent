import { getVersionSession, type VersionSession } from './api/versions';
import { useSessionStore } from '@/stores/useSessionStore';

/** Publish the same authoritative snapshot to the banner and completion indicators. */
export async function refreshSessionAfterStage(
  sid: string,
  version: string | undefined,
  apply: (session: VersionSession) => void,
  isCurrent: () => boolean,
) {
  if (!isCurrent()) return;
  const {data} = await getVersionSession(sid, version);
  if (!isCurrent()) return;
  apply(data);
  useSessionStore.getState().setSession({sd: data, step: data.step});
}

type LabelCompletion = {started?: boolean; mode?: string; progress?: Record<string, {state: string; runId?: string | null}>; legacy?: boolean};
export function labelCompletionKey(overview: LabelCompletion | null): string | null {
  if (!overview?.started || overview.legacy) return null;
  const names = overview.mode === 'model' ? ['infer'] : ['jev', 'gpt'];
  const workers = names.map(name => overview.progress?.[name]);
  return workers.every(worker => worker?.state === 'done')
    ? workers.map((worker, i) => worker?.runId ?? names[i]).join(':') : null;
}
