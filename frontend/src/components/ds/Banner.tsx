import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import { Icon } from "./Icon";
export type BannerProps = { tone?: "info" | "success" | "warning" | "danger"; children: ReactNode; actions?: ReactNode };
const icons = { info: Info, success: CircleCheck, warning: TriangleAlert, danger: CircleAlert };
export function Banner({ tone = "info", children, actions }: BannerProps) { return <div className={`ds-note ${tone}`} role={tone === "danger" ? "alert" : "status"}><span className="ds-ic"><Icon icon={icons[tone]} /></span><div>{children}</div>{actions && <div className="ds-actions">{actions}</div>}</div>; }
