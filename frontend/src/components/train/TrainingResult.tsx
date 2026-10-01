import { embedderLabel } from '@/lib/logic/browserQa';
import { Button, Card, InsightCard, Table } from '@/components/ds';
import type { ModelMetadata } from '@/lib/types';
import { modelDate, mlpDifference, number, percent, record } from './trainingView';
const heads = [['anchor', '대상 경험'], ['sem', '6차원 평균'], ['situation', '상황'], ['signal', '신호'], ['reason', 'Non 사유']];

export function TrainingResult({ model, disabled, onExport }: { model: ModelMetadata; disabled: boolean; onExport: () => void }) {
  const metrics = model.metrics ?? {};
  const difference = mlpDifference(metrics);
  return <div className="grid grid-cols-1 gap-5 lg:grid-cols-12"><div className="lg:col-span-8"><InsightCard eyebrow={`학습 결과 · ${model.modelId}`} insight={`등급 정확도 ${percent(metrics.grade_accuracy)}`} interpretation={<><p>학습 {number(model.n)?.toLocaleString('ko-KR') ?? '확인 불가'}건 · 검증셋 기준입니다.</p><p>Jev 대비 · 멤버 불일치 비율: 확인 불가</p></>} evidence={[{label: '임베딩', value: embedderLabel(model.embedderName ?? model.embedder)}, {label: '규칙', value: String(model.rule_version ?? '—')}, {label: '질문', value: String(model.questions_version ?? '—')}, {label: '생성', value: modelDate(model.createdAt)}]} nextAction={<><span>다음 행동 · 저장하면 클러스터링이 이 결과를 씁니다</span><Button variant="primary" disabled={disabled} onClick={onExport}>저장하고 클러스터링으로</Button></>} /></div><Card className="lg:col-span-4 space-y-3"><h2 className="ds-t-card">헤드별</h2><Table><thead><tr><th scope="col">헤드</th><th scope="col">F1</th><th scope="col">보정 오차</th></tr></thead><tbody>{heads.map(([key, label]) => { const head = record(record(model.perHead)[key]); return <tr key={key}><th scope="row">{label}</th><td>{number(head.f1)?.toFixed(2) ?? '확인 불가'}</td><td>{number(head.ece)?.toFixed(2) ?? '확인 불가'}</td></tr>; })}</tbody></Table><p className="ds-t-caption">선형 멤버 대비 MLP {difference === undefined ? '확인 불가' : `${difference >= 0 ? '+' : ''}${difference.toFixed(1)}%p`}</p>{heads.map(([key, label]) => { const head = record(record(model.perHead)[key]); return head.trained === false ? <p key={key} role="status">{label} 헤드는 표본이 부족해 학습하지 않았습니다({number(head.n) ?? 0}/30). 이 모델로는 분류 모델 방식을 쓸 수 없습니다.</p> : null; })}</Card></div>;
}
