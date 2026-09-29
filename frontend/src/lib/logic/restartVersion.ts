import type { CrawlStatus } from '../api/crawl';

// A completed list still awaits detail collection. Unknown state is checked by the API.
export function crawlBlocksVersion(status?: Pick<CrawlStatus, 'collectionId' | 'kind' | 'status'> | null) {
  return !!status?.collectionId && !(status.kind === 'detail' && status.status === 'done');
}

// Finish all fallible fetching before the caller changes the mounted version.
export async function prepareRestartVersion<T>(create: () => Promise<{version: string}>, load: (version: string) => Promise<{data: T}>) {
  const {version} = await create();
  const {data} = await load(version);
  return {version, data};
}
