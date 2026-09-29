import type { HTMLAttributes } from "react";
export type CardProps = HTMLAttributes<HTMLDivElement> & { size?: "sm" | "md" };
export function Card({ size = "md", className = "", ...props }: CardProps) { return <div {...props} className={`ds-card ${size === "sm" ? "ds-sm" : ""} ${className}`} />; }
