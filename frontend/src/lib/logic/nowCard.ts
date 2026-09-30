import type { Overview } from '../types';
type NowOverview = Pick<Overview, 'started' | 'progress' | 'definitionCheck' | 'now'> & { queue: Pick<Overview['queue'], 'total' | 'estimatedSeconds'> };
export type NowCard = { kind: string; title: string; body: string; action?: { label: string; target: 'start' | 'workers' | 'definitions' | 'queue' | 'audit' | 'training' } };
const estimate = (seconds: number | null | undefined) => seconds == null ? '예상 시간은 판정을 시작하면 표시합니다.' : `예상 ${Math.ceil(seconds / 60).toLocaleString('ko-KR')}분`;
export function pickNowCard(o: NowOverview): NowCard {
 const workers = Object.values(o.progress);
 const times = workers.map(p => p.estimate?.seconds).filter((n): n is number => n != null);
 if(!o.started) return {kind:'before_start',title:'라벨링을 시작하세요',body:`라벨링 방식을 선택하세요. ${estimate(times.length ? Math.max(...times) : null)}`,action:{label:'라벨링 시작',target:'start'}};
 const stopped = workers.find(p => ['paused','failed','interrupted'].includes(p.state));
 if(stopped) return {kind:'paused',title:'판정이 멈췄습니다',body:stopped.reason || '연결과 사용량을 확인하고 이어서 진행하세요.',action:{label:'이어서 진행',target:'workers'}};
 if(o.definitionCheck.needed) return {kind:'definition_check',title:'최근 감사에서 일치도가 두 번 연속 떨어졌습니다',body:o.definitionCheck.reason || '태그 정의를 확인하세요.',action:{label:'태그 정의 보기',target:'definitions'}};
 if(o.queue.total > 0) return {kind:'review',title:`사람이 볼 문서가 ${o.queue.total.toLocaleString('ko-KR')}건 있습니다`,body:estimate(o.queue.estimatedSeconds),action:{label:'검수 시작',target:'queue'}};
 if(o.now.state === 'audit') return {kind:'audit',title:'채택 라벨을 확인하세요',body:'대기 중인 감사 라운드를 진행하세요.',action:{label:'감사 시작',target:'audit'}};
 if(workers.some(p => p.state === 'running' || p.pending > 0)) return {kind:'running',title:'판정 중입니다',body:estimate(times.length ? Math.max(...times) : null)};
 return {kind:'done',title:'라벨링이 끝났습니다',body:'채택한 라벨로 모델을 학습하세요.',action:{label:'학습으로',target:'training'}};
}
