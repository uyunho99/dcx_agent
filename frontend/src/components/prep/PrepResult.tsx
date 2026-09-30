import { Banner, BarList, Button, Card, InsightCard } from '@/components/ds';
import type { PrepStatus } from '@/lib/types';
import { INTERNAL_TOOLS } from '@/lib/internalTools';
import type { PrepReport } from './prep';

export function PrepResult({ report, status, busy, onNext }: { report: PrepReport; status: PrepStatus; busy: boolean; onNext: () => void }) {
  const removed = report.removed;
  const created = report.at ? new Date(report.at) : null;
  const validDate = created && !Number.isNaN(created.getTime());
  const date = validDate ? created.toLocaleDateString('ko-KR') : null;
  const reused = status.reused || (status.status === 'done' && status.runId === null);
  return <section aria-label="전처리 결과" className="space-y-4">
    {reused && <Banner tone="success">같은 규칙의 결과를 그대로 씁니다{date ? `(${date} 생성)` : ''}</Banner>}
    {report.after === 0 && <Banner tone="warning">규칙을 통과한 문서가 없습니다. 광고어와 길이 규칙을 확인하세요.</Banner>}
    <div className="prep-grid">
      <InsightCard eyebrow="전처리 결과" insight={<><span className="ds-num">{report.after.toLocaleString('ko-KR')}</span>건{report.after > 0 ? '이 라벨링으로 넘어갑니다.' : '이 규칙을 통과했습니다.'}</>}
        interpretation={<><p>원본 {report.original.toLocaleString('ko-KR')}건 중 광고 {(removed.ad ?? 0).toLocaleString('ko-KR')} · 너무 짧음 {(removed.too_short ?? 0).toLocaleString('ko-KR')} · 제외 출처 {(removed.excluded_source ?? 0).toLocaleString('ko-KR')} · 중복 {(removed.duplicate ?? 0).toLocaleString('ko-KR')}건을 뺐습니다.</p>{report.embed_failed_zero_vector > 0 && <p className="prep-warning">임베딩 실패 {report.embed_failed_zero_vector.toLocaleString('ko-KR')}건(검색 · 학습에서 제외). 0벡터로 남깁니다.</p>}</>}
        evidence={[{ label: '수집본', value: status.derivedRef?.collectionId ?? '—' }, { label: '', value: `${report.embedder ?? 'voyage-4'} · 1024차원` }, { label: '', value: 'Kiwi' }, { label: '생성', value: validDate ? created.toLocaleString('ko-KR') : '시각 정보 없음' }, ...(INTERNAL_TOOLS ? [{ label: 'prepKey', value: status.derivedRef?.prepKey ?? report.prepKey ?? '—' }] : [])]}
        nextAction={<><span className="ds-t-label">{report.after > 0 ? '다음 행동 · 라벨링을 시작하세요' : '광고어와 길이 규칙을 확인하세요'}</span>{report.after > 0 && <Button variant="primary" loading={busy} onClick={onNext}>라벨링으로 →</Button>}</>} />
      <Card className="space-y-4 prep-removals"><h3 className="ds-t-card">규칙별 제거</h3><BarList highlightIndex={0} items={[["광고어", 'ad'], ['짧음', 'too_short'], ['제외 출처', 'excluded_source'], ['중복', 'duplicate']].map(([label, key]) => ({ label, value: removed[key] ?? 0, displayValue: (removed[key] ?? 0).toLocaleString('ko-KR') }))} /><p className="ds-t-caption">정형 문구 치환 {Object.values(report.boilerplate_replaced).reduce((sum, value) => sum + value, 0).toLocaleString('ko-KR')}건 · 토큰 {report.tokens_written.toLocaleString('ko-KR')}건</p><p className="ds-t-caption">임베딩 완료 {report.embedded.toLocaleString('ko-KR')}건</p></Card>
    </div>
  </section>;
}
