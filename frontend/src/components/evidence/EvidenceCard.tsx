'use client';
import { Badge, Button, Card } from '../ds';
import { contextLabels } from '@/lib/contextLabels';
import type { EvidenceItemView } from '@/lib/types';
import { highlight, locationLabel } from './evidenceView';

export function EvidenceCard({item, readonly, added = false, onAdd}: {
  item: EvidenceItemView; readonly: boolean; added?: boolean; onAdd: (docId: string) => void;
}) {
  const quote = item.quote;
  const segments = highlight(item.text, quote?.verified ? quote.start : null, quote?.verified ? quote.end : null);
  const channel = contextLabels.channels[item.source as keyof typeof contextLabels.channels] ?? item.source;
  return <Card className="min-w-0 space-y-3 break-words">
    <p className="whitespace-pre-wrap">{segments.map((s, i) => s.mark ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>)}</p>
    {quote?.text && !segments.some(s => s.mark) && <blockquote>{quote.text}</blockquote>}
    {quote && !quote.verified && <Badge tone="warning" title="인용 문장을 원문에서 찾지 못해 추론으로 낮췄습니다.">인용 미확인 · 추론</Badge>}
    <div className="flex flex-wrap gap-2"><Badge>{channel}</Badge><Badge>{locationLabel(item.location)}</Badge>
      {item.tags.map(tag => <Badge key={tag}>{tag}</Badge>)}
      {item.band && <Badge>{({core:'중심 원문',fringe:'주변 원문',edge:'가장자리 원문'})[item.band]}</Badge>}
      {item.rare && <Badge>rare</Badge>}
      {item.novelty && <Badge tone="info" title={item.noveltyReason ?? undefined}>새로움 {item.novelty} · 잠정</Badge>}
      {item.knownMatch && item.knownMatch !== 'none' && <Badge>Known Insight와 같은 내용</Badge>}
    </div>
    {item.noveltyReason && <p className="ds-t-caption">{item.noveltyReason}</p>}
    <Button disabled={readonly || added} onClick={() => onAdd(item.docId)}>{added ? 'Known Insight에 추가됨' : 'Known Insight에 추가'}</Button>
  </Card>;
}
