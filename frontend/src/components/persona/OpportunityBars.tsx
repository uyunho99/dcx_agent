import { formatMetric } from './personaView';
import { ProvisionalBadge } from './ProvisionalBadge';
export type OpportunityBar = { id: string; label: string; value: number };
export function OpportunityBars({ bars, mean }: { bars: OpportunityBar[]; mean: number | null }) {
  const ranked = [...bars].sort((a, b) => b.value - a.value);
  const max = Math.max(1,...ranked.map(bar => bar.value),mean ?? 0);
  return <figure style={{margin:0}}><figcaption>기회 순위 <ProvisionalBadge/> · 평균 {formatMetric(mean)}</figcaption>{bars.length ? <svg viewBox={`0 0 600 ${bars.length * 40 + 30}`} role="img" aria-label={`${ranked.map(bar => `${bar.label} ${formatMetric(bar.value)}`).join(', ')}. 평균 ${formatMetric(mean)}`} style={{width:'100%'}}>
    {ranked.map((bar,index) => <g key={bar.id}><text x={0} y={index * 40 + 24} fontSize={12} fill="var(--ink)">{bar.label}</text><rect x={200} y={index * 40 + 8} width={Math.max(0,bar.value) / max * 320} height={20} fill="var(--ink)"/><text x={540} y={index * 40 + 24} fill="var(--ink-strong)" fontSize={12}>{formatMetric(bar.value)}</text></g>)}
    {mean !== null && <line x1={200 + mean / max * 320} x2={200 + mean / max * 320} y1={0} y2={bars.length * 40} stroke="var(--danger)" strokeWidth={2} strokeDasharray="4 3"><title>{`평균 ${formatMetric(mean)}`}</title></line>}
  </svg> : <p>기회 정보가 없습니다.</p>}</figure>;
}
