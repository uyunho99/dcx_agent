import type { PrepConfig, PrepStatus } from '../../lib/types';

type PrepActions = {
  save: (config: PrepConfig) => Promise<unknown>;
  run: () => Promise<PrepStatus>;
  clearDraft: () => Promise<unknown>;
};
export async function executePrep(config: PrepConfig, actions: PrepActions) {
  if (!Number.isInteger(config.minBodyChars) || config.minBodyChars < 0) {
    throw new Error('최소 본문은 0 이상의 정수를 입력하세요.');
  }
  await actions.save(config);
  const status = await actions.run();
  try {
    await actions.clearDraft();
    return { status, draftCleared: true };
  } catch {
    return { status, draftCleared: false };
  }
}
