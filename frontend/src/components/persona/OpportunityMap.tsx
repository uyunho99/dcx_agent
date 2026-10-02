'use client';
import { useState } from 'react';
import type { PersonaMap, PersonaZone } from '../../lib/types';
import { zoneName } from './personaView';
import { ProvisionalBadge } from './ProvisionalBadge';
const shapes = ['circle','square','triangle','diamond','pentagon'];
const symbols = ['●','■','▲','◆','⬟'];
const tones = ['--ink-strong','--ink','--line-strong'];
const x = (value: number) => 60 + value * 480;
const y = (value: number) => 340 - value * 320;
function Shape({ index }: { index: number }) {
  if (index === 1) return <rect x={-7} y={-7} width={14} height={14}/>;
  if (index === 2) return <polygon points="0,-9 8,7 -8,7"/>;
  if (index === 3) return <polygon points="0,-9 9,0 0,9 -9,0"/>;
  if (index === 4) return <polygon points="0,-9 8.6,-2.8 5.3,7.3 -5.3,7.3 -8.6,-2.8"/>;
  return <circle r={7}/>;
}
export type OpportunityMapProps = { map: PersonaMap; highlightedId?: string | null; selectedPersonaId?: string | null; onHighlight?: (id: string | null) => void; onOpenCard?: (personaId: string, contextId: string) => void };
export function OpportunityMap({ map, highlightedId, selectedPersonaId, onHighlight, onOpenCard }: OpportunityMapProps) {
  const [chosen, setChosen] = useState<string[]>([]);
  // Derive presentation order from stable IDs, independent of incoming point order.
  const members = new Map<string, Set<string>>();
  const overlapCounts = new Map<string, number>();
  for (const point of map.points) {
    if (!members.has(point.cluster_id)) members.set(point.cluster_id, new Set());
    members.get(point.cluster_id)!.add(point.persona_id);
    const position = `${point.i}:${point.s}`;
    overlapCounts.set(position, (overlapCounts.get(position) ?? 0) + 1);
  }
  const clusters = [...members.keys()].sort();
  const personaGroups = new Map(clusters.map(cluster => [cluster, [...members.get(cluster)!].sort()]));
  const personas = (cluster: string) => personaGroups.get(cluster)!;
  const toggle = (ids: string[]) => setChosen(current => ids.every(id => current.includes(id)) ? current.filter(id => !ids.includes(id)) : [...new Set([...current,...ids])]);
  const summary = (['A','B','C','D','E','F'] as PersonaZone[]).map(zone => `${zone} ${zoneName(zone)} ${map.points.filter(p => p.zone === zone).length}개`).join(', ');
  const lines = [ [[0,map.base.s_line],[1,map.base.s_line]], map.base.diag1, map.base.diag2 ];
  return <figure style={{ margin: 0, minWidth: 0 }}><figcaption className="ds-t-label">Opportunity Map · Context {map.points.length}개 · 기회 <ProvisionalBadge/></figcaption>
    <svg viewBox="0 0 600 450" role="img" aria-label={`Opportunity Map: ${summary}`} style={{ width:'100%',display:'block' }}>
      <path d="M60 20V340H540" fill="none" stroke="var(--ink)"/>
      {lines.map((line,index) => <line key={index} data-baseline={index} x1={x(line[0][0])} y1={y(line[0][1])} x2={x(line[1][0])} y2={y(line[1][1])} stroke="var(--line-strong)" strokeDasharray="4 4"/>)}
      <text x={300} y={380} textAnchor="middle" fill="var(--ink)">중요도</text><text x={18} y={180} transform="rotate(-90 18 180)" textAnchor="middle" fill="var(--ink)">만족도</text>
      {map.points.map(point => {
        const cluster = clusters.indexOf(point.cluster_id); const tone = personas(point.cluster_id).indexOf(point.persona_id) % 3;
        const highlighted = highlightedId === point.context_id;
        const selected = selectedPersonaId === point.persona_id || chosen.includes(point.persona_id);
        const color = `var(${selected ? '--blue' : tones[tone]})`;
        const count = overlapCounts.get(`${point.i}:${point.s}`)!;
        return <g key={point.context_id} data-context-id={point.context_id} data-highlighted={highlighted} data-shape={shapes[cluster] || 'circle'} transform={`translate(${x(point.i)} ${y(point.s)})`} fill={point.counter ? 'none' : color} stroke={color} strokeWidth={highlighted ? 3 : 2} style={{cursor:'pointer'}} onMouseEnter={() => onHighlight?.(point.context_id)} onMouseLeave={() => onHighlight?.(null)} onClick={() => {onHighlight?.(point.context_id); onOpenCard?.(point.persona_id,point.context_id);}}>
          <title>{`${point.context_id} · ${point.persona_id} · ${point.zone} ${zoneName(point.zone)} · 기회 ${point.odi} (잠정)${point.counter ? " · 반례" : ""}${count > 1 ? ` · 겹친 Context ${count}개` : ""}`}</title>
          {highlighted && <circle r={13} fill="none" strokeDasharray="3 2"/>}<Shape index={cluster}/>
          {point.star && <text x={-5} y={-14} fill={color} stroke="none">★</text>}{cluster >= 5 && <text x={12} y={4} fill={color} stroke="none" fontSize={11}>{point.cluster_id}</text>}
        </g>;
      })}
      {['A 흥미', 'B 경험', 'C 경쟁', 'D 용인', 'E 방치', 'F 위험'].map((label, index) => <text key={label} x={60 + (index % 3) * 160} y={410 + Math.floor(index / 3) * 24} fontSize={12} fill="var(--ink)">{label}</text>)}
    </svg>
    <div aria-label="클러스터와 Persona 범례">{clusters.map((cluster,index) => <div key={cluster} style={{display:'flex', flexWrap:'wrap',gap:8,marginTop:8}}><button type="button" className="ds-chip" aria-pressed={personas(cluster).every(id => chosen.includes(id))} onClick={() => toggle(personas(cluster))}>{symbols[index] || '●'} {cluster}</button>{personas(cluster).map(persona => <button type="button" className="ds-chip" key={persona} aria-label={`Persona ${persona}`} aria-pressed={chosen.includes(persona)} onClick={() => toggle([persona])}>{persona}</button>)}</div>)}</div>
    <p className="ds-t-caption">속 빈 모양 · 반례 Context / ★ 몰랐고 기회도 큰 지점 · 겹친 점은 아래 Context 표에서 각각 확인할 수 있습니다.</p>
  </figure>;
}
