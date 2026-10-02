import { Banner } from '../ds';
import type { EvidenceQuery } from '@/lib/types';
export function QueryPanel({queries,failed}: {queries:EvidenceQuery[];failed:boolean}) {
  return <details className="ds-card min-w-0"><summary>쿼리 보기 · {queries.length}문장</summary>
    {failed && <Banner tone="warning">자동 쿼리 생성에 실패해 Context 이름과 키워드로 검색했습니다.</Banner>}
    <ul className="space-y-2">{queries.map((q,i) => <li key={i}><b>{q.dim}</b> · {q.text}</li>)}</ul>
  </details>;
}
