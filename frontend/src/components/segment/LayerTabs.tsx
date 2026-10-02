"use client";

export type SegmentLayer = "6-A" | "6-B" | "6-C";
export type LayerTabsProps = {
  value: SegmentLayer;
  onChange: (value: SegmentLayer) => void;
  confirm: { clusters: string; personas: string; contexts: string };
};

function isComplete(count: string) {
  const match = /^(\d+)\/(\d+)$/.exec(count);
  return !!match && Number(match[2]) > 0 && Number(match[1]) === Number(match[2]);
}

export function LayerTabs({ value, onChange, confirm }: LayerTabsProps) {
  const clustersDone = isComplete(confirm.clusters);
  const personasDone = clustersDone && isComplete(confirm.personas);
  const items = [
    { value: "6-A", label: "Cluster", title: "클러스터 이름", count: confirm.clusters, locked: false, reason: "" },
    { value: "6-B", label: "Persona", title: "Desire · Goal", count: confirm.personas, locked: !clustersDone, reason: "6-A 확정 후" },
    { value: "6-C", label: "Context", title: "Context 이름 · 행동", count: confirm.contexts, locked: !personasDone, reason: "6-B 확정 후" },
  ] as const;

  return <nav aria-label="층" className="layers" style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, marginBottom: 24 }}>
    {items.map(item => <button key={item.value} type="button" className="layer"
      aria-current={value === item.value ? "step" : undefined}
      aria-disabled={item.locked} title={item.locked ? item.reason : undefined}
      onClick={() => { if (!item.locked) onChange(item.value); }}
      style={{ border: `1px solid var(${value === item.value ? "--blue" : "--line"})`, borderRadius: 10, padding: "10px 14px", textAlign: "left", font: "inherit", cursor: item.locked ? "not-allowed" : "pointer", background: `var(${item.locked ? "--sunken" : value === item.value ? "--blue-soft" : "--paper"})` }}>
      <span className="ds-t-caption" style={{ display: "block", fontWeight: 700, color: !item.locked && isComplete(item.count) ? "var(--success)" : undefined }}>{item.value} · {item.label}</span>
      <span className="ds-t-label" style={{ display: "block", color: `var(${item.locked ? "--sub" : "--ink-strong"})` }}>{item.title}</span>
      <span className="ds-t-caption" style={{ display: "block" }}>{item.locked ? `잠김 · ${item.reason}` : `${item.count} 확정`}</span>
    </button>)}
  </nav>;
}
