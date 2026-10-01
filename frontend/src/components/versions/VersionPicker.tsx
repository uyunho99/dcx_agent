'use client';
import { josa } from '@/lib/logic/josa';
import { Layers } from "lucide-react";
import { useDirty } from "../DirtyProvider";
import { useEffect, useId, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Badge, Button } from '@/components/ds';
import { INTERNAL_TOOLS } from '@/lib/internalTools';
import { useVersion } from './VersionProvider';
import { RestartVersion } from './StageVersion';
import type { Stage, VersionEntry } from '@/lib/api/versions';
export function VersionHistory({entries}: {entries: VersionEntry[]}) {
  const view = useVersion();
  return <ul className="space-y-4">{[...entries].reverse().map(entry => <li className="border-b border-line pb-4 space-y-2" key={entry.id}><div className="flex items-center justify-between gap-2"><strong>{entry.id}</strong><Badge tone={entry.id === view.meta?.activeVersion ? 'info' : 'neutral'}>{entry.readonly ? '읽기 전용' : '활성'}</Badge></div><p className="ds-t-caption">{entry.parent ? `${entry.restartFrom.slice(5)}단계부터 다시` : '처음'} · {new Date(entry.createdAt).toLocaleDateString('ko-KR')}</p>{entry.note && <p>{entry.note}</p>}{INTERNAL_TOOLS && entry.collectionId && <p className="ds-t-caption">수집본 {entry.collectionId}</p>}<Button size="sm" disabled={entry.id === view.version} onClick={() => view.select(entry.id)}>{entry.id} 열기</Button></li>)}</ul>;
}
export function VersionPicker() {
  const view = useVersion(); const [open, setOpen] = useState(false);
  if (!view.meta) return null;
  return <><Button id="version-picker" aria-label={`${view.version} · ${view.readonly ? '읽기 전용' : '활성'} 버전 목록 열기`} title={`${view.version} · ${view.readonly ? '읽기 전용' : '활성'} 버전 목록 열기`} size="sm" style={{whiteSpace:"normal",height:"auto",textAlign:"left"}} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}><Layers size={18} aria-hidden="true" /><span className="pipeline-foot-label">{view.version} · {view.readonly ? '읽기 전용' : '활성'} 버전 목록 열기</span></Button>{view.newerVersion && <p className="ds-t-caption">새 활성 버전 {view.newerVersion}{josa(view.newerVersion, '이/가')} 있습니다. <Button size="sm" onClick={() => view.select(view.newerVersion!)}>{view.newerVersion} 열기</Button></p>}{open && <VersionDrawer onClose={() => setOpen(false)} />}</>;
}
function VersionDrawer({onClose}: {onClose: () => void}) {
  const {confirmNavigation} = useDirty();
  const view = useVersion(); const dialog = useRef<HTMLDialogElement>(null); const id = useId(); const router = useRouter(); const pathname = usePathname();
  const [a, setA] = useState(view.meta?.versions[0]?.id ?? ''); const [b, setB] = useState(view.meta?.activeVersion ?? '');
  const index = ['start','keywords','crawling','preprocess','labeling','training','clustering','personas'].indexOf(pathname.split('/').pop() ?? '');
  const stage = index < 0 ? undefined : `stage${index}` as Stage;
  useEffect(() => { const node = dialog.current; node?.showModal(); return () => {node?.close(); document.getElementById('version-picker')?.focus();}; }, []);
  return <dialog ref={dialog} aria-labelledby={id} className="bg-paper text-ink border border-line rounded-overlay p-6 space-y-6" style={{position:'fixed', inset:'0 0 0 auto', margin:0, width:400, maxWidth:'100vw', height:'100dvh', maxHeight:'100dvh', overflowY:'auto', boxShadow:'var(--shadow-overlay)'}} onCancel={e => {e.preventDefault(); onClose();}}><div className="flex justify-between items-center"><h2 id={id} className="ds-t-card">버전 기록</h2><Button onClick={onClose}>닫기</Button></div><VersionHistory entries={view.meta?.versions ?? []} /><RestartVersion contained stage={stage} from={view.version} label="이 버전에서 새로 시작하기" /><div className="space-y-3">{([[a,setA,'기준 버전'],[b,setB,'비교 버전']] as const).map(([value,set,label]) => <label className="ds-field" key={label}>{label}<select className="ds-inp" value={value} onChange={e => set(e.target.value)}>{view.meta?.versions.map(v => <option key={v.id}>{v.id}</option>)}</select></label>)}<Button disabled={!a || !b || a === b} onClick={() => { if(!confirmNavigation()) return; router.push(`/pipeline/compare?${new URLSearchParams({a,b})}`); onClose(); }}>선택한 버전 비교하기</Button></div></dialog>;
}
