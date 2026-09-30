'use client';
import { josa } from '@/lib/logic/josa';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Badge, Banner, Button, Card, StatGrid, Table, Tabs } from '@/components/ds';
import { compareVersions, getVersionSession, type Stage, type VersionSession } from '@/lib/api/versions';
import { compareView, keywordSnapshotDiff, type KeywordDiff } from '@/lib/logic/compareView';
import { useVersion } from '@/components/versions/VersionProvider';
import { RestartVersion, StaleBanner } from '@/components/versions/StageVersion';
import { VersionHistory } from '@/components/versions/VersionPicker';
import { INTERNAL_TOOLS } from '@/lib/internalTools';
import { contextLabels } from '@/lib/contextLabels';

type CollectionDiff = {same: boolean; before?: string; after?: string; counts?: Record<string, Record<string, number>>};
type FileDiff = {same: boolean; before: Record<string, {savedAt: number}>; after: Record<string, {savedAt: number}>};
const tabs = ['0단계 입력 보기','1단계 키워드 보기','2단계 수집 보기','3단계 이후 보기'];
const fieldNames: Record<string,string> = {bk:'제품명',oneLiner:'한줄 정의',researchQuestion:'리서치 질문',projectType:'프로젝트 성격',analysisGoal:'분석 목적',keyMetrics:'핵심 지표',constraints:'사내 제약',positioning:'브랜드 포지셔닝',channels:'수집 채널',knownInsights:'이미 아는 것',productCategory:'제품군',targetScope:'분석 대상',futureCustomer:'미래 고객'};
export default function ComparePage() { return <Suspense fallback={<p role="status">처리 중…</p>}><CompareScreen /></Suspense>; }
function CompareScreen() {
  const query = useSearchParams(); const view = useVersion(); const a = query.get('a') ?? ''; const b = query.get('b') ?? '';
  const [stage,setStage] = useState<Stage>('stage1'); const [later,setLater] = useState<Stage>('stage3'); const actual = stage === 'stage3' ? later : stage;
  const [result,setResult] = useState<{key: string; data: unknown; session: VersionSession} | null>(null); const [error,setError] = useState(''); const [retry,setRetry] = useState(0);
  const key = `${view.sid}:${a}:${b}:${actual}`;
  const valid = !!view.sid && !!view.meta?.versions.some(v => v.id === a) && !!view.meta?.versions.some(v => v.id === b);
  useEffect(() => {
    if (!valid || !view.sid) return;
    let cancelled = false;
    async function load() {
      try {
        const [raw, right] = await Promise.all([compareVersions<unknown>(view.sid!, a,b,actual), getVersionSession(view.sid!,b)]);
        let data = raw;
        if (actual === 'stage1') {
          const left = await getVersionSession(view.sid!,a);
          data = keywordSnapshotDiff(left.data.keywords ?? [], right.data.keywords ?? []);
        }
        if (!cancelled) {setResult({key,data,session:right.data});setError('');}
      } catch { if (!cancelled) {setResult(null);setError('버전을 비교하지 못했습니다. 다시 확인하세요.');} }
    }
    void load(); return () => {cancelled = true;};
  }, [view.sid,a,b,actual,key,valid,retry]);
  if (!valid) return <Banner>비교할 두 버전을 버전 목록에서 선택하세요.</Banner>;
  const content = error ? <Banner tone="danger" actions={<Button onClick={() => {setError('');setRetry(n=>n+1);}}>다시 확인하기</Button>}>{error}</Banner> : result?.key !== key ? <p role="status">처리 중…</p> : actual === 'stage1' ? <KeywordComparison diff={result.data as KeywordDiff} a={a} b={b} /> : actual === 'stage2' ? <CollectionComparison diff={result.data as CollectionDiff} /> : actual === 'stage0' ? <ContextComparison diff={result.data as Record<string,{before:unknown;after:unknown}>} a={a} b={b} /> : <FileComparison diff={result.data as FileDiff} />;
  const collections = [...new Set(view.meta!.versions.map(v=>v.collectionId).filter(Boolean))];
  return <div className="space-y-6"><header className="flex justify-between items-start gap-6"><div><p className="ds-eyebrow">버전</p><h1 className="ds-t-screen">{a}{josa(a, '와/과')} {b}의 {actual.slice(5)}단계를 비교합니다</h1><p>버전은 세션 내용을 통째로 복사해 만듭니다. 크롤링 수집본은 복사하지 않고 여러 버전이 함께 씁니다.</p></div><RestartVersion stage={actual} from={a} label={`${a}에서 다시 시작하기`} /></header><div className="grid gap-6 lg:grid-cols-3"><Card><h2 className="ds-t-card mb-4">버전 기록</h2><VersionHistory entries={view.meta!.versions} /><h3 className="ds-t-label mt-6">크롤링 수집본</h3>{collections.length ? collections.map((cid,i)=><p key={cid}>{INTERNAL_TOOLS ? cid : `수집본 ${i+1}`} · {view.meta!.versions.filter(v=>v.collectionId===cid).map(v=>v.id).join(' · ')}</p>) : <p>연결된 수집본이 없습니다.</p>}</Card><section className="lg:col-span-2 space-y-6"><Tabs label="비교 단계" value={stage} onChange={v=>setStage(v as Stage)} items={tabs.map((label,i)=>({value:`stage${i}`,label,content:stage===`stage${i}`?<div className="space-y-6 pt-6">{stage==='stage3'&&<label className="ds-field">비교할 단계<select className="ds-inp" value={later} onChange={e=>setLater(e.target.value as Stage)}>{[3,4,5,6,7].map(n=><option key={n} value={`stage${n}`}>{n}단계</option>)}</select></label>}{content}</div>:null}))} />{result?.key === key && <StaleBanner stage={actual} session={result.session} />}</section></div></div>;
}
function KeywordComparison({diff,a,b}: {diff: KeywordDiff;a:string;b:string}) {
  const view = compareView(diff);
  return <><StatGrid items={[{label:'추가',value:view.counts.added},{label:'삭제',value:view.counts.removed},{label:'축 이동',value:view.counts.moved}]} />{view.empty ? <Banner>{view.empty}</Banner> : <Table><thead><tr><th>키워드</th><th>변경</th><th>{a}</th><th>{b}</th></tr></thead><tbody>{view.rows.map((row,i)=><tr key={i}><td className={row.strike?'line-through text-sub':''}>{row.keyword}</td><td><Badge tone={row.tone}>{row.badge}</Badge></td><td>{row.before}</td><td>{row.after}</td></tr>)}</tbody></Table>}<p>축 분포 증감: {view.distribution.map(d=>`${d.label} ${d.delta>0?'+':''}${d.delta}개`).join(' · ') || '변경 없음'}</p></>;
}
function CollectionComparison({diff}: {diff: CollectionDiff}) {
  if (diff.same) return <Banner>같은 수집본</Banner>;
  const rows = Object.entries(diff.counts ?? {}).flatMap(([kw,channels])=>Object.entries(channels).map(([channel,count])=>({kw,channel,count})));
  return <div className="space-y-4"><Banner>서로 다른 수집본입니다.{INTERNAL_TOOLS && ` ${diff.before ?? '없음'} → ${diff.after ?? '없음'}`}</Banner>{rows.length ? <Table><thead><tr><th>키워드</th><th>채널</th><th>건수 증감</th></tr></thead><tbody>{rows.map(r=><tr key={`${r.kw}:${r.channel}`}><td>{r.kw}</td><td>{contextLabels.channels[r.channel as keyof typeof contextLabels.channels] ?? r.channel}</td><td>{r.count>0?'+':''}{r.count}</td></tr>)}</tbody></Table> : <p>비교할 수집 건수가 없습니다.</p>}</div>;
}
const printable = (value: unknown): string => value == null ? '—' : typeof value === 'object' ? Array.isArray(value) ? value.map(printable).join(' · ') : Object.entries(value).map(([key,v])=>`${fieldNames[key] ?? key}: ${printable(v)}`).join(' · ') : String(value);
function ContextComparison({diff,a,b}: {diff:Record<string,{before:unknown;after:unknown}>;a:string;b:string}) { return Object.keys(diff).length ? <Table><thead><tr><th>입력 항목</th><th>{a}</th><th>{b}</th></tr></thead><tbody>{Object.entries(diff).map(([key,value])=><tr key={key}><td>{fieldNames[key] ?? key}</td><td>{printable(value.before)}</td><td>{printable(value.after)}</td></tr>)}</tbody></Table> : <Banner>입력 변경이 없습니다.</Banner>; }
function FileComparison({diff}: {diff: FileDiff}) { const files = [...new Set([...Object.keys(diff.before),...Object.keys(diff.after)])].sort(); return <div className="space-y-4"><Banner>결과 파일이 {diff.same?'같습니다.':'다릅니다.'}</Banner>{files.length ? <Table><thead><tr><th>결과</th><th>이전 저장 시각</th><th>이후 저장 시각</th></tr></thead><tbody>{files.map((file,i)=><tr key={file}><td>{INTERNAL_TOOLS?file:`결과 ${i+1}`}</td>{[diff.before[file],diff.after[file]].map((v,j)=><td key={j}>{v?new Date(v.savedAt*1000).toLocaleString('ko-KR'):'—'}</td>)}</tr>)}</tbody></Table> : <p>저장된 결과 파일이 없습니다.</p>}</div>; }
