import { josa } from '@/lib/logic/josa';
import { Banner, BarList, Button, Card, InsightCard } from '@/components/ds';
import type { Coverage } from '@/lib/api/keywords';
const percent = (v?: number | null) => v == null ? '계산 불가' : `${Math.round(v * 100)}%`;
export function coverageInterpretation(coverage: Coverage): string {
  if (coverage.status === 'loading') return '네이버 자동완성에서 사람 검색어를 받는 중입니다(약 20초).';
  if (coverage.status === 'unavailable') return '네이버 자동완성을 받지 못해 커버리지를 계산할 수 없습니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.';
  if (coverage.status === 'unconnected') {
    return '검색광고가 연결되지 않아 사람 검색어를 받지 못했습니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.';
  }
  return `누락 쿼리 ${coverage.missing_top?.length ?? 0}개가 다음 라운드의 입력에 반영됩니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.`;
}

export function coverageEvidence(c: Coverage) {
  if (c.status === 'unavailable') return [{ label: '실패한 질의', value: `${c.failedSeeds ?? 0}개` }];
  const autocomplete = c.source === 'autocomplete';
  return [
    { label: autocomplete ? '사람 검색어' : '사람 쿼리', value: `${c.humanQueries?.length ?? 0}개` },
    { label: '출처', value: autocomplete ? '네이버 자동완성' : '네이버 검색광고 연관키워드' },
    ...(autocomplete ? [{ label: '가중', value: '순위 가중' }] : []),
    { label: '매칭', value: '부분일치' },
    ...(autocomplete && c.failedSeeds ? [{ label: '질의', value: `${c.seeds ?? 0}개 중 ${c.failedSeeds}개 실패` }] : []),
  ];
}

export function coverageMetrics(c: Coverage) {
  const autocomplete = c.source === 'autocomplete';
  return {
    firstLabel: autocomplete ? '① 순위 가중' : '① 검색량 가중',
    bandTitle: autocomplete ? '② 순위 구간별 커버리지' : '② 검색량 구간별 커버리지',
    bands: autocomplete
      ? (c.m2_bands ?? []).map(({ label, value }) => ({ label, value: value ?? 0, displayValue: value == null ? '—' : percent(value) }))
      : (c.m2 ?? []).map((v, i) => ({ label: `${i + 1}분위`, value: v ?? 0, displayValue: percent(v) })),
    m7: autocomplete && c.m7_reason === 'no_volume' ? '계산 불가(검색량 없음)' : percent(c.m7),
  };
}

// The caller starts this only for loading coverage; terminal responses stop it.
export function startCoveragePolling<T extends { coverage: Coverage }>(read: () => Promise<T>, receive: (result: T) => void, reportError: (error: unknown) => void) {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout>;
  async function poll() {
    try {
      const result = await read();
      if (cancelled) return;
      receive(result);
      if (result.coverage.status !== 'loading') return;
    } catch (error) { if (!cancelled) reportError(error); }
    if (!cancelled) timer = setTimeout(poll, 3000);
  }
  timer = setTimeout(poll, 3000);
  return () => { cancelled = true; clearTimeout(timer); };
}

export function CoveragePanel({ coverage: c, onRefresh, busy, beforeR3 }: { coverage: Coverage; onRefresh: () => void; busy: boolean; beforeR3: boolean }) {
  const loading = c.status === 'loading';
  const autocomplete = c.source === 'autocomplete';
  const metrics = coverageMetrics(c);
  return <div className="kw-coverage">
    {beforeR3 && c.status === 'unconnected' && <Banner>미연결 · 검색광고 API가 연결되지 않았습니다. 커버리지 없이 R3을 생성합니다.</Banner>}
    {c.status === 'failed' && <Banner tone="warning">커버리지 조회에 실패했습니다. 다시 계산하세요.</Banner>}
    {beforeR3 && c.status === 'connected' && c.humanQueries?.length === 0 && <Banner>비교할 사람 검색어가 없습니다. 이 입력 없이 R3을 생성합니다.</Banner>}
    <InsightCard eyebrow="커버리지 신호" insight={c.status === 'unavailable' || c.m1 == null ? '커버리지 계산 불가' : `사람들이 많이 찾는 표현의 ${percent(c.m1)}${josa(percent(c.m1), '을/를')} 덮고 있습니다.`} interpretation={<span aria-live="polite">{coverageInterpretation(c)}</span>} evidence={coverageEvidence(c)} nextAction={<><span>누락 쿼리를 확인하고 다음 라운드를 생성하세요.</span><Button size="sm" loading={busy || loading} onClick={onRefresh}>다시 계산하기</Button></>} />
    <Card style={loading ? { opacity: 0.5 } : undefined}><h3 className="ds-t-card">지표 요약</h3><dl className="kw-metrics"><dt>{metrics.firstLabel}</dt><dd>{percent(c.m1)}</dd><dt>⑥ 축 분포 차이 (JS)</dt><dd>{c.m6 == null ? '계산 불가' : c.m6.toFixed(2)}</dd><dt>⑦ LLM 단독</dt><dd>{metrics.m7}</dd></dl><h3 className="ds-t-card">{metrics.bandTitle}</h3><BarList max={1} items={metrics.bands} /></Card>
    <div className="kw-table-wrap"><table className="kw-table"><caption>다음 라운드에 반영할 누락 쿼리</caption><thead><tr><th scope="col">{autocomplete ? '사람 검색어' : '사람 쿼리'}</th><th scope="col">{autocomplete ? '자동완성 순위' : '월간 검색수'}</th></tr></thead><tbody>{c.missing_top?.map(([query, volume]) => <tr key={query}><td>{query}</td><td>{volume.toLocaleString('ko-KR')}</td></tr>)}</tbody></table>{!c.missing_top?.length && <p className="ds-t-caption">{autocomplete ? (c.status === 'connected' ? '자동완성 검색어를 모두 덮고 있습니다.' : null) : '표시할 누락 쿼리가 없습니다.'}</p>}</div>
  </div>;
}
