'use client';
import { Button } from '../ds/Button';
import { ProgressBar } from '../ds/ProgressBar';
import { workerActions, type WorkerAction } from './workerControls';
import type { LabelProgress } from '@/lib/types';
export function LabelerProgress({name, progress, onControl, busy = false}: {name: string; progress: LabelProgress; onControl?: (action: WorkerAction) => void; busy?: boolean}) {
 const waiting = ['none', 'pending', 'idle'].includes(progress.state);
 const done = progress.done ?? 0;
 const pending = progress.total === undefined ? progress.pending : Math.max(0, progress.total - done);
 const stopped = ['paused','failed','interrupted','cancelled'].includes(progress.state);
 return <section aria-label={`${name} 판정 진행`}><h3 className="ds-t-card">{name}</h3><ProgressBar label={`${name} 판정 진행`} value={waiting ? 0 : progress.progress === undefined ? undefined : progress.progress * 100}/><p>{done.toLocaleString('ko-KR')}{progress.total !== undefined && ` / ${progress.total.toLocaleString('ko-KR')}`}건 판정 · {pending.toLocaleString('ko-KR')}건 남음</p><p>{waiting ? '대기 중' : progress.state === 'done' ? '판정을 마쳤습니다.' : stopped ? '판정이 멈췄습니다.' : '처리 중…'}</p>{progress.reason && <p role="status">{progress.reason}</p>}{progress.estimate?.seconds != null && <p className="ds-t-caption">예상 {Math.ceil(progress.estimate.seconds / 60).toLocaleString('ko-KR')}분</p>}{onControl && workerActions(progress.state).map(action => <Button key={action} disabled={busy} onClick={() => onControl(action)}>{action === 'resume' ? '이어서 진행' : action === 'pause' ? '일시 정지' : '중단'}</Button>)}</section>;
}
