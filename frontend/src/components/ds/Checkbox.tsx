"use client";
import { useEffect, useRef, type InputHTMLAttributes } from "react";
export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label: string; indeterminate?: boolean };
export function Checkbox({ label, indeterminate = false, className = "", ...props }: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = indeterminate; }, [indeterminate]);
  return <label className={`ds-check ${className}`}><input {...props} type="checkbox" ref={ref} aria-checked={indeterminate ? "mixed" : props.checked} />{label}</label>;
}
