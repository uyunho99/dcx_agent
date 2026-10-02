import { Badge } from "../ds/Badge";

export type QualityBadgesProps = {
  layer?: "L1" | "L2" | "L3";
  quality: { cohesion?: number | null; boundary?: number | null; ari?: number | null; npmi?: number | null; flags?: string[] };
};

export function QualityBadges({ quality, layer = "L1" }: QualityBadgesProps) {
  const metrics = [
    { label: "응집", value: quality.cohesion, threshold: 0.6, warning: "분리 검토" },
    { label: "경계", value: quality.boundary, threshold: 0.15, warning: "경계 검토", percent: true },
    { label: "안정", value: quality.ari, threshold: layer === "L2" ? 0.6 : 0.7, warning: "불안정" },
    { label: "NPMI", value: quality.npmi, threshold: -Infinity, warning: "" },
  ];
  return <div className="qrow" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
    {metrics.map(({ label, value, threshold, warning, percent }) => {
      if (value == null || !Number.isFinite(value)) return null;
      const warn = percent ? value > threshold : value < threshold;
      return <Badge key={label} tone={warn ? "warning" : "neutral"}>{label} {percent ? `${Math.round(value * 100)}%` : value.toFixed(2)}{warn ? ` · ${warning}` : ""}</Badge>;
    })}
  </div>;
}
