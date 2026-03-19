"use client";
import { useState, useEffect, useRef, useCallback } from "react";

interface UsePollingOptions<T> {
  fetcher: () => Promise<T>;
  interval: number;
  enabled: boolean;
  shouldStop?: (data: T) => boolean;
}

export function usePolling<T>({ fetcher, interval, enabled, shouldStop }: UsePollingOptions<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      setLoading(true);
      const result = await fetcher();
      setData(result);
      if (shouldStop?.(result)) {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch {
      // silently fail polling
    } finally {
      setLoading(false);
    }
  }, [fetcher, shouldStop]);

  useEffect(() => {
    if (!enabled) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    poll();
    timerRef.current = setInterval(poll, interval);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [enabled, interval, poll]);

  const refresh = useCallback(() => {
    poll();
  }, [poll]);

  return { data, loading, refresh };
}
