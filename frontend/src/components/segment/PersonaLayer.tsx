'use client';
import { Badge, Banner, Button, Card, Input } from '../ds';
import type { SegmentCluster, SegmentPersona } from '@/lib/types';
import { Representatives, type EditorProps } from './ClusterLayer';
import { WordNetwork } from './WordNetwork';
export function PersonaLayer({ personas, clusters = [], selected, onSelect, disabled, edits, onEdit, onConfirm }: EditorProps & {
    personas: SegmentPersona[];
    clusters?: SegmentCluster[];
    selected: string;
    onSelect: (id: string) => void;
}) {
    const p = personas.find(p => p.id === selected) ?? personas[0];
    if (!p)
        return <Card>Persona가 없습니다.</Card>;
    const edit = edits[p.id];
    const name = edit?.name ?? p.name ?? p.nameDraft ?? '';
    const desire = edit?.desire ?? p.desire ?? p.desireDraft ?? '';
    const goals = edit?.goals ?? (p.goals.length ? p.goals : p.goalsDraft);
    return <div className="grid grid-cols-[minmax(160px,1fr)_minmax(0,3fr)] gap-5"><aside className="space-y-4 min-w-0">
      <nav aria-label="클러스터 목록" className="space-y-2">
        <h2 className="ds-t-label">클러스터</h2>
        {Array.from(new Set(personas.map(row => row.clusterId))).map(id => {
          const rows = personas.filter(row => row.clusterId === id);
          const cluster = clusters.find(row => row.id === id);
          return <Button key={id} className="w-full whitespace-normal text-left" aria-current={p.clusterId === id ? 'true' : undefined} onClick={() => onSelect(rows[0].id)}>
            {cluster?.name ?? cluster?.nameDraft ?? id} · {rows.filter(row => row.confirmed).length}/{rows.length} 확정
          </Button>;
        })}
      </nav>
      <nav aria-label="Persona 목록" className="space-y-2">
        <h2 className="ds-t-label">Persona</h2>
        {personas.filter(row => row.clusterId === p.clusterId).map(row => <Button className="w-full whitespace-normal text-left" key={row.id} aria-current={p.id === row.id ? 'true' : undefined} onClick={() => onSelect(row.id)}>{row.name ?? row.nameDraft ?? row.id} · {row.confirmed ? '확정됨' : '초안'}</Button>)}
      </nav>
    </aside><div className="min-w-0 space-y-4"><Card><WordNetwork network={p.network}/><p className="break-words">중심 어휘 · {p.centrality.map(([w, s]) => `${w} ${s.toFixed(2)}`).join(' · ')}</p></Card>{p.flags.includes('unstable') && <Badge tone="warning">불안정</Badge>}{p.flags.includes('few_communities') && <Banner>어휘 네트워크가 하나로 묶여 Persona를 나누지 않았습니다.</Banner>}<Card className="space-y-4"><p>{p.id} · 문서 {p.docs}건 · 작성자 {p.authors}명</p>{p.confirmed && !edit && <Badge tone="success">확정됨</Badge>}{(!p.nameDraft || !p.desireDraft) && !p.confirmed && <Banner tone="warning">초안을 만들지 못했습니다. 직접 입력하세요.</Banner>}<Input label="Persona 이름" value={name} disabled={disabled} onChange={e => onEdit(p.id, { name: e.target.value })}/><Input label="Desire" value={desire} disabled={disabled} onChange={e => onEdit(p.id, { desire: e.target.value })}/>{(goals.length ? goals : ['']).map((goal, i) => <div key={i} className="flex items-end gap-2"><div className="min-w-0 flex-1"><Input label={`Goal ${i + 1}`} value={goal} disabled={disabled} onChange={e => { const next = goals.length ? [...goals] : ['']; next[i] = e.target.value; onEdit(p.id, { goals: next }); }}/></div>{goals.length > 1 && <Button disabled={disabled} onClick={() => onEdit(p.id, { goals: goals.filter((_, j) => i !== j) })}>삭제</Button>}</div>)}<Button disabled={disabled || goals.length >= 3} onClick={() => onEdit(p.id, { goals: [...(goals.length ? goals : ['']), ''] })}>Goal 추가</Button><Representatives reps={p.reps}/>{'hint' in p && typeof p.hint === 'string' && <Banner>초안 힌트: {p.hint}</Banner>}{p.similar.map(s => <Banner key={s.id}>{s.id} “{s.desire}”와 Desire가 비슷합니다({s.score.toFixed(2)}). <span>클러스터가 달라 합치지 않고 기록만 남깁니다.</span></Banner>)}<Button variant="primary" disabled={disabled || !name.trim() || !desire.trim() || !goals.length || goals.some(g => !g.trim())} onClick={() => onConfirm(p.id)}>Desire · Goal 확정</Button></Card></div></div>;
}
