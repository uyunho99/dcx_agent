"use client";
import { useId } from "react";
export type SwitchProps = { label: string; checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean; id?: string };
export function Switch({ label, checked, onChange, disabled, id }: SwitchProps) {
  const generated = useId(); const controlId = id ?? generated;
  return <div className="ds-toggle"><button id={controlId} type="button" className="ds-sw" role="switch" aria-checked={checked} aria-labelledby={`${controlId}-label`} disabled={disabled} onClick={() => onChange(!checked)} /><label id={`${controlId}-label`} htmlFor={controlId} className="ds-t-label">{label}</label></div>;
}
