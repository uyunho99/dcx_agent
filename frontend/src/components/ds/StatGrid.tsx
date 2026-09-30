import type { ReactNode } from "react";
export type StatGridProps = { items: { label: string; value: ReactNode; hint?: string }[] };
export function StatGrid({ items }: StatGridProps) { return <dl className="ds-stats">{items.map((item, index) => <div className="ds-stat" key={`${item.label}-${index}`}><dt className="ds-t-label">{item.label}</dt><dd className="ds-v">{item.value}</dd>{item.hint && <dd className="ds-t-caption">{item.hint}</dd>}</div>)}</dl>; }
