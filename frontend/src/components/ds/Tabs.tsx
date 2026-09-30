"use client";
import { useId, type ReactNode } from "react";
export type TabsProps = { label: string; value: string; onChange: (value: string) => void; items: { value: string; label: string; count?: number; disabled?: boolean; content: ReactNode }[] };
export function Tabs({ label, value, onChange, items }: TabsProps) {
  const id = useId(); const enabled = items.filter(item => !item.disabled);
  return <><div className="ds-tabs" role="tablist" aria-label={label}>{items.map((item, index) => <button type="button" className="ds-tab" key={item.value} role="tab" id={`${id}-tab-${index}`} aria-controls={`${id}-panel-${index}`} aria-selected={value === item.value} disabled={item.disabled} tabIndex={value === item.value || (!enabled.some(i => i.value === value) && enabled[0]?.value === item.value) ? 0 : -1} onClick={() => onChange(item.value)} onKeyDown={event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); const i = enabled.findIndex(o => o.value === item.value);
    const next = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 : (i + (event.key === "ArrowLeft" ? -1 : 1) + enabled.length) % enabled.length;
    onChange(enabled[next].value); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")[next]?.focus();
  }}>{item.label}{item.count !== undefined && <span className="ds-num">{item.count}</span>}</button>)}</div>{items.map((item, index) => <div key={item.value} role="tabpanel" id={`${id}-panel-${index}`} aria-labelledby={`${id}-tab-${index}`} hidden={value !== item.value} tabIndex={0}>{item.content}</div>)}</>;
}
