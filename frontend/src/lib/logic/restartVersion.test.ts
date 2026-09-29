import { expect, it, vi } from 'vitest';
import { prepareRestartVersion } from './restartVersion';

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
