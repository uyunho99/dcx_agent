'use client';
import { Button } from '../ds/Button';
import { ProgressBar } from '../ds/ProgressBar';
import type { LabelProgress } from '@/lib/types';
export function LabelerProgress({name, progress, onControl, busy = false}: {name: string; progress: LabelProgress; onControl?: (action: 'pause' | 'resume') => void; busy?: boolean}) {
 const stopped = ['paused','failed','interrupted'].includes(progress.state);
 return <section aria-label={`${name} 판정 진행`}><h3 className="ds-t-card">{name}</h3><ProgressBar label={`${name} 판정 진행`} value={progress.progress === undefined ? undefined : progress.progress * 100}/><p>{progress.done?.toLocaleString('ko-KR') ?? 0}건 판정 · {progress.pending.toLocaleString('ko-KR')}건 남음</p><p>{progress.state === 'done' ? '판정을 마쳤습니다.' : stopped ? '판정이 멈췄습니다.' : '처리 중…'}</p>{progress.reason && <p role="status">{progress.reason}</p>}{progress.estimate?.seconds != null && <p className="ds-t-caption">예상 {Math.ceil(progress.estimate.seconds / 60).toLocaleString('ko-KR')}분</p>}{onControl && (stopped || progress.state === 'running') && <Button loading={busy} onClick={() => onControl(stopped ? 'resume' : 'pause')}>{stopped ? '이어서 진행' : '일시 정지'}</Button>}</section>;
}
