"use client";
import type { KeyboardEvent } from "react";
export type ChoiceOption = { value: string; label: string; disabled?: boolean };
export type ChoiceChipsProps = { label: string; options: ChoiceOption[]; className?: string } & ({ multiple?: false; value: string; onChange: (value: string) => void } | { multiple: true; value: string[]; onChange: (value: string[]) => void });
export function ChoiceChips(props: ChoiceChipsProps) {
  const enabled = props.options.filter(option => !option.disabled);
  const selected = (value: string) => props.multiple ? props.value.includes(value) : props.value === value;
  function onKey(event: KeyboardEvent<HTMLButtonElement>, value: string) {
    if (props.multiple || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); const index = enabled.findIndex(option => option.value === value);
    const next = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 : (index + (["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1) + enabled.length) % enabled.length;
    props.onChange(enabled[next].value);
    const buttons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"); buttons?.[next]?.focus();
  }
  return <div className={`ds-chips ${props.className ?? ""}`} role={props.multiple ? "group" : "radiogroup"} aria-label={props.label}>{props.options.map(option => <button key={option.value} type="button" className="ds-chip" disabled={option.disabled} role={props.multiple ? undefined : "radio"} aria-pressed={props.multiple ? selected(option.value) : undefined} aria-checked={props.multiple ? undefined : selected(option.value)} tabIndex={props.multiple || selected(option.value) || (!enabled.some(o => selected(o.value)) && enabled[0]?.value === option.value) ? 0 : -1} onKeyDown={event => onKey(event, option.value)} onClick={() => { if (props.multiple) props.onChange(selected(option.value) ? props.value.filter(v => v !== option.value) : [...props.value, option.value]); else props.onChange(option.value); }}>{option.label}</button>)}</div>;
}
