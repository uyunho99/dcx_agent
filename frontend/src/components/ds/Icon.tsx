import type { LucideIcon, LucideProps } from "lucide-react";
export type IconProps = LucideProps & { icon: LucideIcon; label?: string };
export function Icon({ icon: Glyph, label, size = 16, ...props }: IconProps) { return <Glyph size={size} strokeWidth={1.5} {...props} aria-hidden={label ? undefined : true} aria-label={label} role={label ? "img" : undefined} />; }
