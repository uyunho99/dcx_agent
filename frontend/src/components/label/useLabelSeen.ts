import { useEffect, useRef } from 'react';
import { markLabelSeen } from '@/lib/api/label';
import { displayError } from '@/lib/api/errors';

// Scoped to the open screen: polling and StrictMode replay must not reset the baseline.
export function useLabelSeen(sid: string, version: string | undefined, readonly: boolean, onError: (message: string) => void) {
  const seen = useRef(new Set<string>());
  useEffect(() => {
    const key = JSON.stringify([sid, version]);
    if (readonly || seen.current.has(key)) return;
    seen.current.add(key);
    void markLabelSeen(sid, version).catch(error => onError(displayError(error)));
  }, [sid, version, readonly, onError]);
}
