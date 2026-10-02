import { Badge, type BadgeProps } from "./Badge";

export type ProvisionalBadgeProps = Omit<BadgeProps, "children" | "tone">;
export function ProvisionalBadge(props: ProvisionalBadgeProps) {
  return <Badge {...props} tone="neutral">잠정</Badge>;
}
