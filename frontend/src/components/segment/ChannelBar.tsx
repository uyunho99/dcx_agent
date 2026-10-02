import { Badge } from "../ds/Badge";
import { contextLabels } from "@/lib/contextLabels";
import { INTERNAL_TOOLS } from "@/lib/internalTools";

export type ChannelBarProps = { channels: Record<string, number> };
const shades = ["#1c1e22", "#7f838b", "#b9bcc2", "#dfe1e5"];

export function ChannelBar({ channels }: ChannelBarProps) {
  const entries = Object.entries(channels).filter(([source, share]) => (INTERNAL_TOOLS || source !== "fixture") && Number.isFinite(share) && share > 0);
  if (!entries.length) return <p className="ds-t-caption">채널 정보가 없습니다.</p>;
  const description = entries.map(([source, share]) => `${contextLabels.channels[source as keyof typeof contextLabels.channels] ?? source} ${Number((share * 100).toFixed(1))}%`).join(" · ");
  return <div>
    <div className="chanbar" aria-hidden="true" style={{ display: "flex", height: 8, borderRadius: 999, overflow: "hidden", background: "var(--sunken)", margin: "6px 0 4px" }}>
      {entries.map(([source, share], index) => <span key={source} style={{ width: `${Math.min(share, 1) * 100}%`, background: shades[index % shades.length] }} />)}
    </div>
    <p className="ds-t-caption" style={{ margin: 0 }}>{entries.some(([, share]) => share >= 0.8) && <><Badge tone="warning">한 채널 편중</Badge>{" "}</>}{description}</p>
  </div>;
}
