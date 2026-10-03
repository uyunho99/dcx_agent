export type KSuggestChartProps = { k: number; silhouette: Record<number, number>; sample: number };

export function KSuggestChart({ k, silhouette, sample }: KSuggestChartProps) {
  const entries = Object.entries(silhouette)
    .map(([candidate, score]) => ({ k: Number(candidate), score }))
    .filter(point => Number.isFinite(point.k) && Number.isFinite(point.score))
    .sort((a, b) => a.k - b.k);
  if (!entries.length) return <p className="ds-t-caption">실루엣 정보가 없습니다.</p>;
  const min = Math.min(...entries.map(point => point.score));
  const max = Math.max(...entries.map(point => point.score));
  const points = entries.map((point, index) => ({ ...point,
    x: entries.length === 1 ? 140 : 30 + index * 225 / (entries.length - 1),
    y: max === min ? 55 : 85 - (point.score - min) / (max - min) * 60,
  }));
  return <figure style={{ margin: 0 }}>
    <figcaption className="ds-t-label">k = {k}를 제안한 근거</figcaption>
    <p className="ds-t-caption" style={{ margin: "4px 0 16px" }}>표본 {sample.toLocaleString("ko-KR")}건 · 실루엣 최대</p>
    <svg viewBox="0 0 280 120" role="img" aria-label={`k별 실루엣: ${points.map(point => `k ${point.k}: ${point.score}`).join(", ")}. 제안 k = ${k}`} style={{ display: "block", width: "100%" }}>
      <line x1="20" y1="100" x2="270" y2="100" stroke="var(--line)" />
      <polyline fill="none" stroke="var(--sub)" strokeWidth="2" points={points.map(point => `${point.x},${point.y}`).join(" ")} />
      {points.map(point => <g key={point.k}>
        <circle cx={point.x} cy={point.y} r={point.k === k ? 5 : 2} fill={point.k === k ? "var(--blue)" : "var(--sub)"} />
        <text x={point.x} y="115" fontSize="11" fill="var(--sub)" textAnchor="middle">{point.k}</text>
        {point.k === k && <text x={point.x} y={point.y - 10} fontSize="11" fill="var(--ink-strong)" textAnchor="middle">{Number(point.score).toFixed(2)}</text>}
      </g>)}
    </svg>
  </figure>;
}
