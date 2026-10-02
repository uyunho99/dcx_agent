import { ProvisionalBadge } from './ProvisionalBadge';
export const radarAxes = { Computed: '맞춤형 서비스가 필요해', Connected: '실시간으로 직접 보고 싶어', Shared: '함께 즐기고 싶어' } as const;
export type RadarValues = Record<keyof typeof radarAxes, { raw: number | null; percentile: number | null }>;
export function Radar({ values }: { values: RadarValues }) {
  const axes = Object.keys(radarAxes) as (keyof RadarValues)[];
  const coord = (index: number, value: number) => { const angle = -Math.PI / 2 + index * Math.PI * 2 / 3; return `${150 + Math.cos(angle) * 85 * value},${115 + Math.sin(angle) * 85 * value}`; };
  const safe = (value: number | null) => value !== null && Number.isFinite(value) ? Math.max(0,Math.min(1,value)) : 0;
  const label = axes.map(axis => `${axis}: 원값 ${values[axis].raw ?? '—'}, 백분위 ${values[axis].percentile ?? '—'}`).join(', ');
  return <figure style={{margin:0}}><figcaption>레이더 <ProvisionalBadge/></figcaption><svg viewBox="0 0 300 240" role="img" aria-label={label} style={{width:'100%',maxWidth:360}}>
    {[.25,.5,.75,1].map(level => <polygon key={level} points={axes.map((_,index) => coord(index,level)).join(' ')} fill="none" stroke="var(--line)"/>)}
    <polygon points={axes.map((axis,index) => coord(index,safe(values[axis].raw))).join(' ')} fill="var(--ink)" fillOpacity={.15} stroke="var(--ink-strong)"/>
    <polygon points={axes.map((axis,index) => coord(index,safe((values[axis].percentile ?? 0) / 100))).join(' ')} fill="none" stroke="var(--ink)" strokeDasharray="4 4"/>
    {axes.map((axis,index) => {const [cx,cy]=coord(index,1.25).split(',');return <text key={axis} x={cx} y={cy} textAnchor="middle" fontSize={11} fill="var(--ink)">{axis}</text>;})}
  </svg><p className="ds-t-caption">실선 · 원값 / 점선 · 백분위</p><dl>{axes.map(axis => <div key={axis}><dt>{axis} · {radarAxes[axis]}</dt><dd>원값 {values[axis].raw ?? '—'} · 백분위 {values[axis].percentile ?? '—'}</dd></div>)}</dl></figure>;
}
