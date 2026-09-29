"use client";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./Button";
export type PopoverProps = { label: string; triggerLabel: string; open: boolean; onOpenChange: (open: boolean) => void; children: ReactNode };
export function Popover({ label, triggerLabel, open, onOpenChange, children }: PopoverProps) {
  const id = useId(); const trigger = useRef<HTMLButtonElement>(null); const panel = useRef<HTMLDivElement>(null); const wasOpen = useRef(false);
  useEffect(() => {
    if (open) { panel.current?.focus(); wasOpen.current = true; }
    else if (wasOpen.current) { trigger.current?.focus(); wasOpen.current = false; }
  }, [open]);
  useEffect(() => {
    if (!open) return;
    function escape(event: KeyboardEvent) { if (event.key === "Escape") { event.preventDefault(); onOpenChange(false); } }
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [open, onOpenChange]);
  return <div className="ds-pop-anchor"><button ref={trigger} type="button" className="ds-btn" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => onOpenChange(!open)}>{triggerLabel}</button>{open && <div ref={panel} id={id} className="ds-pop" role="dialog" aria-label={label} tabIndex={-1}>{children}<div className="ds-actions"><Button size="sm" variant="quiet" onClick={() => onOpenChange(false)}>닫기</Button></div></div>}</div>;
}
