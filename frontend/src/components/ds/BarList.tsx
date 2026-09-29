export type BarListProps = { items: { label: string; value: number; displayValue?: string }[]; max?: number; highlightIndex?: number };
export function BarList({ items, max, highlightIndex }: BarListProps) {
  const ceiling = Math.max(1, max ?? Math.max(...items.map(item => Number.isFinite(item.value) ? item.value : 0)));
  return <div className="ds-bars">{items.map((item, index) => <div className="ds-bar" key={`${item.label}-${index}`}><span className="ds-t-label">{item.label}</span><div className="ds-track" aria-hidden="true"><div className={`ds-fill ${index === highlightIndex ? "ds-hi" : ""}`} style={{ width: `${Number.isFinite(item.value) ? Math.min(100, Math.max(0, item.value / ceiling * 100)) : 0}%` }} /></div><span className="ds-v ds-t-label">{item.displayValue ?? item.value}</span></div>)}</div>;
}
