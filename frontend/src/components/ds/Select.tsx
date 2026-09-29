"use client";
import { useId, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: string; error?: string };
export function Select({ label, hint, error, id, children, className = "", ...props }: SelectProps) {
  const generated = useId(); const fieldId = id ?? generated;
  const description = [props["aria-describedby"], (error || hint) && `${fieldId}-message`].filter(Boolean).join(" ") || undefined;
  return <div className="ds-field"><label htmlFor={fieldId}>{label}{props.required && <span className="ds-req">*</span>}</label><div className="ds-select"><select {...props} id={fieldId} aria-invalid={error ? true : props["aria-invalid"]} aria-describedby={description} className={`ds-inp ${error ? "ds-error" : ""} ${className}`}>{children}</select><ChevronDown size={16} strokeWidth={1.5} aria-hidden="true" /></div>{(error || hint) && <span id={`${fieldId}-message`} className={error ? "ds-err" : "ds-hint"}>{error || hint}</span>}</div>;
}
