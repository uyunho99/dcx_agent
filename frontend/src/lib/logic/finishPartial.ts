import type { CrawlStatus } from '../api/crawl';
type PartialStatus = Pick<CrawlStatus,'kind'|'status'|'resumable'|'channels'|'remaining_by_channel'>;
const pausedChannels = (status:PartialStatus) => Object.entries(status.channels).filter(([,c])=>['paused_blocked','paused_parse_error'].includes(c.status));
export function canFinishPartial(status:PartialStatus) {
 const paused=pausedChannels(status).map(([s])=>s);
 return status.kind==='detail' && !['running','stopping'].includes(status.status) && status.resumable!==false && paused.length>0 && !!status.remaining_by_channel && Object.entries(status.remaining_by_channel).every(([s,n])=>!n||paused.includes(s));
}
export function skippedSummary(name:string,count:number,reason?:string|null) {
 return `${name} ${count.toLocaleString('ko-KR')}건 미수집(${reason==='parse_error'?'파싱 오류':'차단'})`;
}
export function finishPartialConfirmation(status:PartialStatus,names:Record<string,string>) {
 return pausedChannels(status).map(([s,c])=>skippedSummary(names[s]??s,status.remaining_by_channel?.[s]??0,c.status.replace('paused_',''))).join('\n')+'\n남은 URL을 건너뛰고 지금까지 모은 결과로 마치시겠습니까?';
}
