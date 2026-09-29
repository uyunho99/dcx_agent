import { expect, it, vi } from 'vitest';
import { createActionQueue } from './actionQueue';

it('preserves a waiting review/move and resolves only when it finishes', async () => {
  const enqueue = createActionQueue();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const first = enqueue(() => held);
  const review = vi.fn(async () => {});
  const move = vi.fn(async () => {});
  const second = enqueue(review);
  const third = enqueue(move);
  await Promise.resolve();
  expect(review).not.toHaveBeenCalled();
  expect(move).not.toHaveBeenCalled();
  release();
  await Promise.all([first, second, third]);
  expect(review).toHaveBeenCalledOnce();
  expect(move).toHaveBeenCalledOnce();
  expect(review.mock.invocationCallOrder[0]).toBeLessThan(move.mock.invocationCallOrder[0]);
});
it('propagates errors without losing the next queued action', async () => {
  const enqueue = createActionQueue();
  const failed = enqueue(async () => { throw new Error('failed'); });
  const next = vi.fn(async () => {});
  const pending = enqueue(next);
  await expect(failed).rejects.toThrow('failed');
  await pending;
  expect(next).toHaveBeenCalledOnce();
});
