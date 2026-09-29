import type { CSSProperties } from "react";
export type SkeletonProps = { width?: CSSProperties["width"]; height?: CSSProperties["height"]; radius?: "input" | "button" | "card" | "overlay" | "full"; className?: string };
export function Skeleton({ width = "100%", height = 24, radius = "card", className = "" }: SkeletonProps) { return <div aria-hidden="true" className={`ds-skeleton ${className}`} style={{ width, height, borderRadius: `var(--r-${radius})` }} />; }
