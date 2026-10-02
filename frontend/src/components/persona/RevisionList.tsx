'use client';
const sourceLabel = (by?: string) => ({generate:'생성',chat:'채팅 수정',revert:'되돌리기'}[by ?? ''] ?? by);
function localDate(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '날짜 없음' : new Intl.DateTimeFormat('ko-KR', {year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date);
}
export type RevisionEntry = { revision: number; message?: string; by?: string; createdAt?: string };
export function RevisionList({ revisions, currentRevision, onView, onRevert, busy = false }: { revisions: RevisionEntry[]; currentRevision: number; onView: (revision: number) => void; onRevert: (revision: number) => void; busy?: boolean }) {
  return <section aria-label="판 목록"><h3 className="ds-t-card">판 목록</h3><ul style={{listStyle:'none',padding:0}}>{revisions.map(entry => <li key={entry.revision} aria-current={entry.revision === currentRevision ? 'true' : undefined} style={{display:'flex',flexWrap:'wrap',gap:8,padding:'8px 0',borderBottom:'1px solid var(--line)'}}><span>판 {entry.revision} {entry.message} {sourceLabel(entry.by)} {localDate(entry.createdAt)}{entry.revision === currentRevision && ' · 현재'}</span><button type="button" className="ds-btn ds-quiet ds-sm" disabled={busy} onClick={() => onView(entry.revision)}>판 {entry.revision} 보기</button><button type="button" className="ds-btn ds-secondary ds-sm" disabled={busy || entry.revision === currentRevision} onClick={() => onRevert(entry.revision)}>이 판으로 되돌리기</button></li>)}</ul>{!revisions.length && <p>저장된 판이 없습니다.</p>}</section>;
}
