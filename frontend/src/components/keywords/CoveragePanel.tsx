import { Banner, BarList, Button, Card, InsightCard } from '@/components/ds';
import type { Coverage } from '@/lib/api/keywords';
const percent = (v?: number | null) => v == null ? '계산 불가' : `${Math.round(v * 100)}%`;
export function CoveragePanel({ coverage: c, onRefresh, busy }: { coverage: Coverage; onRefresh: () => void; busy: boolean }) {
  return <div className="kw-coverage">
    {c.status === 'unconnected' && <Banner>미연결 · 검색광고 API가 연결되지 않았습니다. 커버리지 없이 R3를 생성합니다.</Banner>}
    {c.status === 'failed' && <Banner tone="warning">커버리지 조회에 실패했습니다. 다시 계산하세요.</Banner>}
    {c.status === 'connected' && c.humanQueries?.length === 0 && <Banner>비교할 사람 검색어가 없습니다. 이 입력 없이 R3를 생성합니다.</Banner>}
    <InsightCard eyebrow="커버리지 신호" insight={c.m1 == null ? '커버리지 계산 불가' : `사람들이 많이 찾는 표현의 ${percent(c.m1)}를 덮고 있습니다.`} interpretation={`누락 쿼리 ${c.missing_top?.length ?? 0}개가 다음 라운드의 입력에 반영됩니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.`} evidence={[{ label: '사람 쿼리', value: `${c.humanQueries?.length ?? 0}개` }, { label: '출처', value: '네이버 검색광고 연관키워드' }, { label: '매칭', value: '부분일치' }]} nextAction={<><span>누락 쿼리를 확인하고 다음 라운드를 생성하세요.</span><Button size="sm" loading={busy} onClick={onRefresh}>다시 계산하기</Button></>} />
    <Card><h3 className="ds-t-card">지표 요약</h3><dl className="kw-metrics"><dt>① 검색량 가중</dt><dd>{percent(c.m1)}</dd><dt>⑥ 축 분포 차이 (JS)</dt><dd>{c.m6 == null ? '계산 불가' : c.m6.toFixed(2)}</dd><dt>⑦ LLM 단독</dt><dd>{percent(c.m7)}</dd></dl><h3 className="ds-t-card">② 검색량 구간별 커버리지</h3><BarList max={1} items={(c.m2 ?? []).map((v, i) => ({ label: `${i + 1}분위`, value: v ?? 0, displayValue: percent(v) }))} /></Card>
    <div className="kw-table-wrap"><table className="kw-table"><caption>다음 라운드에 반영할 누락 쿼리</caption><thead><tr><th scope="col">사람 쿼리</th><th scope="col">월간 검색수</th></tr></thead><tbody>{c.missing_top?.map(([query, volume]) => <tr key={query}><td>{query}</td><td>{volume.toLocaleString('ko-KR')}</td></tr>)}</tbody></table>{!c.missing_top?.length && <p className="ds-t-caption">표시할 누락 쿼리가 없습니다.</p>}</div>
  </div>;
}
