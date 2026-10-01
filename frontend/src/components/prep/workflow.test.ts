import { describe, expect, it, vi } from 'vitest';
import { executePrep } from './workflow';
import { prepConfig } from './prep';

describe('preparation execution', () => {
  it('saves config before running and clears the draft only after the run is accepted', async () => {
    const calls: string[] = [];
    const result = { status: 'done' as const, progress: 1, runId: null, reused: true };
    const outcome = await executePrep(prepConfig({}), {
      save: async () => { calls.push('config'); }, run: async () => { calls.push('run'); return result; },
      clearDraft: async () => { calls.push('draft'); },
    });
    expect(calls).toEqual(['config', 'run', 'draft']);
    expect(outcome).toEqual({ status: result, draftCleared: true });
  });
  it('does not run when config saving fails', async () => {
    const run = vi.fn(); const clearDraft = vi.fn();
    await expect(executePrep(prepConfig({}), { save: async () => { throw Error('save'); }, run, clearDraft })).rejects.toThrow('save');
    expect(run).not.toHaveBeenCalled(); expect(clearDraft).not.toHaveBeenCalled();
  });
  it('keeps a started job visible if clearing the draft fails', async () => {
    const status = { status: 'running' as const, progress: 0, runId: 'r1' };
    await expect(executePrep(prepConfig({}), { save: async () => {}, run: async () => status, clearDraft: async () => { throw Error('offline'); } })).resolves.toEqual({ status, draftCleared: false });
  });
  it('rejects invalid minimum lengths before any request', async () => {
    const save = vi.fn();
    for (const minBodyChars of [NaN, -1, 1.5]) {
      await expect(executePrep({ ...prepConfig({}), minBodyChars }, { save, run: vi.fn(), clearDraft: vi.fn() })).rejects.toThrow('0 이상의 정수');
    }
    expect(save).not.toHaveBeenCalled();
  });
});
