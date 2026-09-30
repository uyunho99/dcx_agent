import type { Axis, Destination } from '@/lib/api/keywords';
export const axes: { value: Axis; label: string }[] = [{ value: 'physical', label: '물리' }, { value: 'psychological', label: '심리' }, { value: 'behavioral', label: '행동' }];
const subs: Record<Axis, [string, string][]> = {
  physical: [['time', '시간'], ['space', '공간'], ['social', '사회적 환경'], ['sense', '감각'], ['body', '신체 상태'], ['product_physical', '제품·물리 상호작용']],
  psychological: [['emotion', '감정'], ['goal_ladder', '표면 목표·기능적 결과·숨은 니즈'], ['perceived_risk', '심리적 장벽'], ['belief', '인지·신념'], ['identity', '자아·정체성']],
  behavioral: [['trigger', '기존 행동·문제 발생·트리거'], ['constraint', '제약'], ['coping', '대처·우회'], ['info_search', '정보탐색'], ['switching', '전환·이탈']],
};
export const destinations: Destination[] = axes.flatMap(a => subs[a.value].map(([sub]) => ({ axis: a.value, sub })));
export const groupKey = (d: Destination) => `${d.axis}/${d.sub}`;
export const subLabel = (d: Destination) => subs[d.axis].find(([sub]) => sub === d.sub)?.[1] ?? d.sub.replace(/^custom:/, '');
export const groupLabel = (d: Destination) => `${axes.find(a => a.value === d.axis)?.label} › ${subLabel(d)}`;
export const badgeLabels: Record<string, string> = { llm_only: 'LLM 단독', low_volume: '검색량 적음', unconnected: '미연결', misclassified_suspect: '오분류 의심', 'misclassified-suspect': '오분류 의심', misclassified: '오분류 의심' };
