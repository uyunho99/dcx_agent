import type { CrawlStatus } from '../api/crawl';

// Completed list gates allow a fresh collection fork (D-096).
export function crawlBlocksVersion(status?: Pick<CrawlStatus, 'collectionId' | 'kind' | 'status' | 'resumable'> | null) {
  return !!status?.collectionId && !((status.kind === 'detail' || status.kind === 'list') && status.status === 'done' && !status.resumable);
}

// Older status responses expose interruption through status and channel pauses.
export function crawlCanResume(status: Pick<CrawlStatus, 'status' | 'resumable'>, paused = false) {
  return status.resumable ?? (status.status === 'interrupted' || status.status === 'paused' || paused);
}

// Finish all fallible fetching before the caller changes the mounted version.
export async function prepareRestartVersion<T>(create: () => Promise<{version: string}>, load: (version: string) => Promise<{data: T}>) {
  const {version} = await create();
  const {data} = await load(version);
  return {version, data};
}
