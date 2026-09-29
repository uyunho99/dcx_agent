"use client";
import { useEffect, useId, type ReactNode } from "react";
import { Button } from "@/components/ds";
import { useDirty } from "./DirtyProvider";
export function SaveBar({ dirty, valid, saving, onDraft, onSave, primary }: {
  dirty: boolean; valid: boolean; saving?: boolean; onDraft: () => void; onSave: () => void; primary: ReactNode;
}) {
  const {register} = useDirty(); const id = useId();
  useEffect(() => {register(id, dirty); return () => register(id, false);}, [register,id,dirty]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  return <div className="flex flex-wrap items-center gap-3 py-6" role="region" aria-label="저장 작업">
    <span className="ds-t-caption" role="status">{dirty ? "저장되지 않은 변경 있음" : "변경 사항 없음"}</span>
    <Button onClick={onDraft}>임시 저장</Button>
    <Button disabled={!valid} loading={saving} onClick={onSave}>저장</Button>
    {primary}
  </div>;
}
