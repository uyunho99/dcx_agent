"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { INTERNAL_TOOLS } from "@/lib/internalTools";

export type IntegrationStatus = {
  name: string;
  connected: boolean;
  env_vars: string[];
  affects: string[];
  last_error: string | null;
};

export async function getIntegrations(signal?: AbortSignal): Promise<IntegrationStatus[]> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/integrations`, { signal, cache: "no-store" });
  if (!response.ok) throw new Error("외부 API 연결 상태를 불러오지 못했습니다.");
  const data: unknown = await response.json();
  if (!Array.isArray(data) || !data.every(item =>
    item && typeof item.name === "string" && typeof item.connected === "boolean" &&
    Array.isArray(item.env_vars) && item.env_vars.every((value: unknown) => typeof value === "string") &&
    Array.isArray(item.affects) && item.affects.every((value: unknown) => typeof value === "string") &&
    (item.last_error === null || typeof item.last_error === "string")
  )) throw new Error("외부 API 연결 상태를 불러오지 못했습니다.");
  // Retain only the public metadata contract, never additional response fields.
  return data.map(({ name, connected, env_vars, affects, last_error }) => ({ name, connected, env_vars, affects, last_error }));
}

export function useIntegrations() {
  const [entries, setEntries] = useState<IntegrationStatus[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const active = useRef<AbortController | null>(null);
  const recheck = useCallback(async () => {
    if (!INTERNAL_TOOLS) return;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setLoading(true);
    setError(false);
    try {
      const result = await getIntegrations(controller.signal);
      if (!controller.signal.aborted) setEntries(result);
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void recheck();
    return () => active.current?.abort();
  }, [recheck]);
  return { entries, loading, error, recheck };
}
