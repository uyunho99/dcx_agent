import type { Draft } from '../api/keywords';
export const restoreKeywordDraft = (draft: Draft | undefined, gen: number) => draft?.gen === gen ? {...draft, direction: draft.direction ?? ''} : undefined;
