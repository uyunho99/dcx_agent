'use client';
import { useRef, useState } from 'react';
import { Button, Card, Table } from '@/components/ds';
import { Queue } from './Queue';
import { KappaTable } from './KappaTable';
import { createAudit } from '@/lib/api/label';
import { displayError } from '@/lib/api/errors';
import type { Overview } from '@/lib/types';

export function Audit({sid, version, overview: o, readonly = false, oneLiner, onRefresh}: {sid: string; version?: string; overview: Overview; readonly?: boolean; oneLiner?: string; onRefresh: () => void}) {
  const [round, setRound] = useState<number | undefined>();
  const [mode, setMode] = useState<'audit' | 'reissue'>('audit');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  async function create() {
    if (readonly || lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {const result = await createAudit(sid, version); if(result.round != null) {setRound(result.round); setMode('audit');} onRefresh();}
    catch(e) {setError(displayError(e));}
    finally {lock.current = false; setBusy(false);}
  }
  return <div className="space-y-6">
    {o.definitionCheck.needed && <p role="status">최근 감사에서 일치도가 두 번 연속 떨어졌습니다. {o.definitionCheck.reason} 태그 정의를 확인하세요.</p>}
    {o.audit.some(r => r.round === 1 && r.n >= 50) && <Card><p>첫 감사 라운드를 마쳤습니다. 일치도가 낮은 칸의 태그 정의를 확인하고, 정의를 수정하려면 새 버전에서 다시 시작하세요. 이미 제출한 판정은 이전 버전에 남습니다.</p></Card>}
    <Card className="space-y-4"><div className="flex flex-wrap items-center justify-between gap-4"><h2 className="ds-t-card">라운드별 일치도 (κ_AI · 등급)</h2><Button disabled={readonly || o.accepted < 50} loading={busy} onClick={() => void create()}>새 라운드 만들기 · 50건</Button></div>
      <p>첫 자동 감사는 채택 1,000건에서 시작하며, 이후 1만 건마다 50건을 확인합니다.</p>
      {error && <p role="alert">{error}</p>}
      <Table><thead><tr><th>라운드</th><th>표본</th><th>등급 κ</th><th>비고</th><th>판정</th></tr></thead><tbody>{o.audit.map(r => <tr key={r.round}><th scope="row">{r.round}</th><td>{r.n}건</td><td>{r.kappaAI.grade.kappa?.toFixed(2) ?? '표본 부족'}</td><td>{r.kappaAI.grade.n < 30 ? '표본 30건부터 확인하세요' : r.kappaAI.grade.kappa != null && r.kappaAI.grade.kappa < .75 ? '기준 0.75 미만 · 정의 확인' : '—'}</td><td><Button onClick={() => {setRound(r.round); setMode('audit');}}>라운드 열기</Button></td></tr>)}</tbody></Table>
      {!o.audit.length && <p>아직 감사 라운드가 없습니다.</p>}
      <p>κ 추이: {o.audit.map(r => `${r.round}회 ${r.kappaAI.grade.kappa?.toFixed(2) ?? '표본 부족'}`).join(' → ') || '감사 후 표시합니다.'}</p>
    </Card>
    <Card><h2 className="ds-t-card">자기 일관성 (re-issue)</h2><p>라운드마다 이전 감사 문서 2건을 다시 판정합니다.</p><p>표본 {o.selfConsistency.n}건 · 일치율 {o.selfConsistency.agree == null ? '표본 부족' : `${(o.selfConsistency.agree * 100).toFixed(1)}%`}</p></Card>
    <div className="flex flex-wrap gap-3"><Button aria-pressed={mode === 'audit'} onClick={() => setMode('audit')}>감사 판정</Button><Button aria-pressed={mode === 'reissue'} onClick={() => setMode('reissue')}>이전 감사 다시 판정</Button><Button onClick={() => setRound(undefined)}>전체 대기 라운드</Button></div>
    <p>감사에서는 AI 판정을 숨긴 채 독립적으로 판정합니다. 제출한 판정은 즉시 저장됩니다.{round != null && ` · 라운드 ${round}`}</p>
    <div className="grid items-start gap-6 lg:grid-cols-3"><div className="lg:col-span-2"><Queue key={`${mode}:${round}`} sid={sid} version={version} overview={o} mode={mode} round={round} readonly={readonly} onSubmitted={onRefresh}/></div><Card data-focus-zone="panel" className="space-y-3"><h2 className="ds-t-card">태그 정의</h2>{oneLiner && <p>{oneLiner}</p>}<dl className="space-y-3">{definitions.map(([name, definition]) => <div key={name}><dt className="ds-t-label">{name}</dt><dd>{definition}</dd></div>)}</dl></Card></div>
    <Card><KappaTable audit={(o.audit.find(r => r.round === round) ?? o.audit.at(-1))?.kappaAI} jev={o.labelerAccuracy.jev} gpt={o.labelerAccuracy.gpt}/></Card>
  </div>;
}

// Wording mirrors the shared q1 definitions; grading remains exclusively server-side.
const definitions = [
  ["대상 경험", "첫 줄 [맥락]의 대상에 관한 구체적인 경험이나 필요가 있으면 1이다. 대상과 연결되지 않은 일반적인 말이나 단순 언급은 0이다."],
  ["감각", "대상 경험에서 감각으로 지각한 특성이 구체적으로 드러나면 1이다. 감각 근거 없는 좋다·나쁘다 같은 평가만 있으면 0이다."],
  ["감정", "대상 경험과 연결된 감정과 그 계기가 드러나면 1이다. 감정어 단독은 0이다."],
  ["판단", "대상 경험에 대한 판단, 비교, 기대 또는 해석과 그 근거가 드러나면 1이다. 근거 없는 평가어 나열은 0이다."],
  ["행동", "대상 경험과 연결된 실제 행동, 시도 또는 구체적인 대응이 드러나면 1이다. 대상과 무관한 행동은 0이다."],
  ["관계", "대상 경험과 연결된 타인과의 관계, 상호작용 또는 사회적 맥락이 드러나면 1이다. 관계 경험 없이 타인을 단순 언급하면 0이다."],
  ["결과", "대상 경험 이후의 구체적인 결과나 변화가 드러나면 1이다. 결과 없이 기대나 희망만 말하면 0이다."],
  ["상황", "대상 경험이 발생한 때, 장소, 조건 또는 목적이 구체적으로 드러나면 1이다. 경험 조건 없는 막연한 말은 0이다."],
  ["Non 사유", "anchor=1이고 여섯 의미 태그 중 하나 이상이 1이면 not_non이다. 나머지는 Non이며 가장 직접적인 사유를 고른다. 각 사유는 해당 근거가 있으면 1, 없으면 0으로 판단한다. 비판어 단독은 필요나 경험 근거로 세지 않는다."],
  ["신호", "Core·Supporting일 때만 여섯 의미 태그의 근거로 신호를 고른다. 해당 신호의 구체적인 근거가 있으면 1, 없으면 0이다. 감정어 단독은 0이며 신호 근거가 아니다. Non이면 null로 둔다."],
];
