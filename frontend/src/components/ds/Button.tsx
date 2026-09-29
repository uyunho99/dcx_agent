import type { ButtonHTMLAttributes } from "react";
export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet"; size?: "sm" | "md"; loading?: boolean };
export function Button({ variant = "secondary", size = "md", loading = false, disabled, className = "", children, ...props }: ButtonProps) {
  return <button type="button" {...props} disabled={disabled || loading} aria-busy={loading || undefined} className={`ds-btn ds-${variant} ${size === "sm" ? "ds-sm" : ""} ${className}`}>{loading ? "처리 중…" : children}</button>;
}
