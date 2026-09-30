import { Fragment, type ReactNode } from "react";
export type EvidenceMetaProps = { items: { label: string; value: ReactNode }[] };
export function EvidenceMeta({ items }: EvidenceMetaProps) { return <div className="ds-meta">{items.map((item, index) => <Fragment key={`${item.label}-${index}`}>{index > 0 && <span className="ds-sep" aria-hidden="true" />}<span>{item.label} {item.value}</span></Fragment>)}</div>; }
