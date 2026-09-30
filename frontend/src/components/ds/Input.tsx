"use client";
import { useId, type InputHTMLAttributes } from "react";
export type InputProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string };
export function Input({ label, hint, error, id, className = "", ...props }: InputProps) {
  const generated = useId(); const fieldId = id ?? generated;
  const description = [props["aria-describedby"], (error || hint) && `${fieldId}-message`].filter(Boolean).join(" ") || undefined;
  return <div className="ds-field"><label htmlFor={fieldId}>{label}{props.required && <span className="ds-req">*</span>}</label><input {...props} id={fieldId} aria-invalid={error ? true : props["aria-invalid"]} aria-describedby={description} className={`ds-inp ${error ? "ds-error" : ""} ${className}`} />{(error || hint) && <span id={`${fieldId}-message`} className={error ? "ds-err" : "ds-hint"}>{error || hint}</span>}</div>;
}
