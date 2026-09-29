import { expect, it, vi } from 'vitest';
import { crawlBlocksVersion, prepareRestartVersion } from './restartVersion';

it('loads the created snapshot before returning a version for selection', async () => {
  const events: string[] = [];
  const result = await prepareRestartVersion(async () => { events.push('create'); return {version: 'v3'}; }, async version => { events.push(`load ${version}`); return {data: {step: 'r1'}}; });
  expect(events).toEqual(['create', 'load v3']);
  expect(result).toEqual({version: 'v3', data: {step: 'r1'}});
});
it('propagates snapshot errors without reaching selection', async () => {
  const select = vi.fn();
  await expect(prepareRestartVersion(async () => ({version: 'v3'}), async () => { throw new Error('snapshot failed'); }).then(select)).rejects.toThrow('snapshot failed');
  expect(select).not.toHaveBeenCalled();
});

it('blocks known unfinished collections but leaves unknown state to the API', () => {
  for (const status of ['running', 'stopping', 'stopped', 'interrupted', 'paused', 'failed']) {
    expect(crawlBlocksVersion({collectionId: 'c1', kind: 'detail', status})).toBe(true);
  }
  expect(crawlBlocksVersion({collectionId: 'c1', kind: 'list', status: 'done'})).toBe(true);
  expect(crawlBlocksVersion({collectionId: 'c1', kind: 'detail', status: 'done'})).toBe(false);
  expect(crawlBlocksVersion({kind: null, status: 'idle'})).toBe(false);
  expect(crawlBlocksVersion(null)).toBe(false);
});
