"use client";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, type ReactNode, type Ref, type MouseEventHandler } from "react";
import { Button } from "./Button";
import { observePopover } from "./popoverMeasure";
export type PopoverTrigger = {
  ref: Ref<HTMLButtonElement>;
  props: {
    type: "button";
    "aria-haspopup": "dialog";
    "aria-expanded": boolean;
    "aria-controls": string | undefined;
    onClick: MouseEventHandler<HTMLButtonElement>;
  };
};
export type PopoverProps = {
  label: string;
  contained?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
} & (
  | { triggerLabel: string; renderTrigger?: (trigger: PopoverTrigger) => ReactNode }
  | { triggerLabel?: string; renderTrigger: (trigger: PopoverTrigger) => ReactNode }
);
// Custom triggers must forward ref and spread props onto a focusable button.
export function Popover({ contained = false, label, triggerLabel, renderTrigger, open, onOpenChange, children }: PopoverProps) {
  const id = useId(); const trigger = useRef<HTMLButtonElement>(null); const panel = useRef<HTMLDivElement>(null); const wasOpen = useRef(false);
  const setTriggerRef = useCallback((node: HTMLButtonElement | null) => { trigger.current = node; }, []);
  useLayoutEffect(() => {
    const node = panel.current;
    if (!open || contained || !node) return;
    return observePopover(node, trigger.current);
  }, [open, contained]);
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
  const triggerProps: PopoverTrigger["props"] = {
    type: "button",
    "aria-haspopup": "dialog",
    "aria-expanded": open,
    "aria-controls": open ? id : undefined,
    onClick: () => onOpenChange(!open),
  };
  return <div className={contained ? "ds-pop-anchor ds-pop-contained" : "ds-pop-anchor"}>{renderTrigger ? renderTrigger({ ref: setTriggerRef, props: triggerProps }) : <button ref={trigger} className="ds-btn" {...triggerProps}>{triggerLabel}</button>}{open && <div ref={panel} id={id} className="ds-pop" data-align="end" role="dialog" aria-label={label} tabIndex={-1}>{children}<div className="ds-actions"><Button size="sm" variant="quiet" onClick={() => onOpenChange(false)}>닫기</Button></div></div>}</div>;
}
