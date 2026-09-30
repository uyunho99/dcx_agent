import type { HTMLAttributes } from "react";
export type BadgeProps = HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "info" | "success" | "warning" | "danger"; pill?: boolean };
export function Badge({ tone = "neutral", pill, className = "", ...props }: BadgeProps) { return <span {...props} className={`ds-badge ds-${tone} ${pill ? "ds-pill" : ""} ${className}`} />; }
