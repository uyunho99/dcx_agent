'use client';
import { useEffect, useRef } from 'react';
import { useVersion } from './VersionProvider';

/** A completion key identifies a result; repeated status polls must not re-fetch it. */
export function useStageCompletionRefresh(completion: string | null) {
  const {readonly, refreshSessionAfterStage} = useVersion();
  const previous = useRef<string | null>(null);
  useEffect(() => {
    const changed = completion !== previous.current;
    previous.current = completion;
    if (!readonly && completion && changed) {
      // The provider presents refresh failures through its existing retry UI.
      void refreshSessionAfterStage().catch(() => {});
    }
  }, [completion, readonly, refreshSessionAfterStage]);
}
