import type { ReactNode } from "react";
import { Card } from "./Card";
import { EvidenceMeta, type EvidenceMetaProps } from "./EvidenceMeta";
export type InsightCardProps = { eyebrow: string; insight: ReactNode; interpretation: ReactNode; evidence: EvidenceMetaProps["items"]; nextAction: ReactNode };
export function InsightCard({ eyebrow, insight, interpretation, evidence, nextAction }: InsightCardProps) { return <Card className="ds-insight"><div className="ds-eyebrow">{eyebrow}</div><h2 className="ds-t-insight">{insight}</h2><div className="ds-t-body">{interpretation}</div><EvidenceMeta items={evidence} /><div className="ds-nextact">{nextAction}</div></Card>; }
