'use client';
import { useRef, useState, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Banner, Button, Card, Input, Popover } from '@/components/ds';
import { createVersion, getVersionSession, type Stage, type VersionSession } from '@/lib/api/versions';
import { useSessionStore } from '@/stores/useSessionStore';
import type { CrawlConfig, CrawlStatus } from '@/lib/api/crawl';
import { contextLabels } from '@/lib/contextLabels';
import { INTERNAL_TOOLS } from '@/lib/internalTools';
import { stalePageStage } from '@/lib/logic/qaFix';
import { displayError } from '@/lib/api/errors';
import { crawlBlocksVersion, prepareRestartVersion } from '@/lib/logic/restartVersion';
import { useVersion } from './VersionProvider';
import { useDirty } from "../DirtyProvider";
import { restartLabelNotice } from '@/lib/logic/browserQa';
const routes = ['start','keywords','crawling','preprocess','labeling','training','clustering','evidence','personas'];
export function RestartVersion({stage, from, label = '이 단계부터 다시', disabled = false, crawlStatus, contained = false}: {stage?: Stage; from?: string; label?: string; disabled?: boolean; crawlStatus?: CrawlStatus | null; contained?: boolean}) {
  const {confirmNavigation} = useDirty();
  const view = useVersion(); const router = useRouter(); const [open, setOpen] = useState(false); const [note, setNote] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const lock = useRef(false);
  const [chosenStage, setChosenStage] = useState<Stage | ''>('');
  const restartStage = stage ?? chosenStage;
  const crawlBlocked = crawlBlocksVersion(crawlStatus);
  const blocked = disabled || busy || crawlBlocked;
  const blockedTitle = crawlBlocked ? '크롤링 수집을 끝낸 뒤 새 버전을 만드세요.' : disabled ? '읽기 전용 버전입니다.' : busy ? '새 버전을 만들고 있습니다.' : undefined;
  if (!view.sid || !view.meta) return null;
  async function restart() {
    if (blocked || lock.current || !restartStage || !confirmNavigation()) return; lock.current = true; setBusy(true); setError('');
    try {
      const {version, data} = await prepareRestartVersion(
        () => createVersion(view.sid!, from ?? view.meta!.activeVersion, restartStage, note),
        version => getVersionSession(view.sid!, version),
      );
      useSessionStore.getState().setSession({sd: data, step: data.step, projectContext: data.projectContext ?? null});
      router.push(`/pipeline/${routes[Number(restartStage.slice(5))] ?? 'start'}`); setOpen(false);
      view.select(version, true);
    } catch (e) { setError(displayError(e, '새 버전을 만들지 못했습니다. 버전 목록을 확인하고 다시 시도하세요.')); }
    finally {lock.current = false; setBusy(false);}
  }
  return <Popover contained={contained} label="새 버전 만들기" open={open} onOpenChange={value => {if (!value || !blocked) setOpen(value);}} renderTrigger={({ref, props}) => <button ref={ref} {...props} className="ds-btn ds-secondary" aria-disabled={blocked} title={blockedTitle}>{label}</button>}><div className="space-y-3">{!stage && <label className="ds-field">다시 시작할 단계<select className="ds-inp" value={chosenStage} disabled={busy} onChange={e => setChosenStage(e.target.value as Stage)}><option value="">단계 선택</option>{routes.map((route, i) => <option key={route} value={`stage${i}`}>{i}단계</option>)}</select></label>}<Input label="다시 시작하는 이유" hint="메모는 선택 입력입니다." value={note} disabled={busy} onChange={e => setNote(e.target.value)} />{error && <Banner tone="danger">{error}</Banner>}<Button variant="primary" loading={busy} disabled={blocked || !restartStage} onClick={() => void restart()}>새 버전 만들기</Button></div></Popover>;
}
export function StageVersionAction({stage, crawlStatus}: {stage: Stage; crawlStatus?: CrawlStatus | null}) { const view = useVersion(); return <div className="flex justify-end"><RestartVersion stage={stage} crawlStatus={crawlStatus} disabled={view.readonly} /></div>; }
export function StaleBanner({stage, session}: {stage: Stage; session: VersionSession | null}) {
  const view = useVersion(); const pageStage = stalePageStage(stage, session?.stale); const stale = pageStage ? session?.stale?.[pageStage] : undefined; const match = stale?.match(/stage(\d+) changed in (v\d+)/);
  const source = view.meta?.versions.find(v => v.id === match?.[2])?.parent ?? session?.parentVersion ?? session?.version;
  const notice = stage === 'stage4' ? restartLabelNotice(session) : null;
  if (notice) return <Banner>{notice}</Banner>;
  return stale ? <Banner tone="warning">이 결과는 {source}의 {pageStage?.slice(5)}단계 기준입니다. 이 단계를 다시 하거나 그대로 쓰세요.</Banner> : null;
}
export function VersionBanner({stage}: {stage: Stage}) {
  const view = useVersion();
  return <>{view.readonly && <Banner>{view.version} · 읽기 전용 · <RestartVersion stage={stage} from={view.version} label="이 버전에서 새로 시작하기" /></Banner>}<StaleBanner stage={stage} session={view.session} /></>;
}
export function VersionStage({stage, children, showBanner = true}: {stage: Stage; children: ReactNode; showBanner?: boolean}) {
  const view = useVersion();
  const [openedReadonly] = useState(view.readonly);
  return <div className="space-y-4">{showBanner && <VersionBanner stage={stage} />}<fieldset disabled={view.readonly} className="min-w-0" onClickCapture={e => {if(view.readonly){e.preventDefault();e.stopPropagation();}}} onDragStartCapture={e => {if(view.readonly)e.preventDefault();}} onDropCapture={e => {if(view.readonly){e.preventDefault();e.stopPropagation();}}}>{stage === 'stage2' && openedReadonly ? <HistoricalCrawl /> : children}</fieldset></div>;
}
function HistoricalCrawl() {
  const {session} = useVersion();
  const config = session?.crawlConfig as Partial<CrawlConfig> | undefined;
  const channelName = (channel: string) => contextLabels.channels[channel as keyof typeof contextLabels.channels] ?? channel;
  return <div className="space-y-6"><header><StageVersionAction stage="stage2" /><p className="ds-eyebrow">2단계 · 크롤링</p><h1 className="ds-t-screen">저장된 수집 설정을 확인합니다</h1></header><Card><h2 className="ds-t-card">크롤링 수집본</h2><p>{session?.collectionId ? '기존 수집본 사용 중' : '연결된 수집본이 없습니다.'}</p>{INTERNAL_TOOLS && session?.collectionId && <p>{session.collectionId}</p>}<p className="ds-t-caption">과거 버전의 실시간 수집 상태는 제공되지 않습니다. 버전 비교에서 수집본 차이를 확인하세요.</p></Card>{config ? <Card className="space-y-4"><h2 className="ds-t-card">수집 설정</h2><Input label="수집 채널" value={config.channels?.filter(c => INTERNAL_TOOLS || c !== 'fixture').map(channelName).join(' · ') ?? ''} readOnly /><div className="grid gap-4 md:grid-cols-2"><Input label="시작일" value={config.dateFrom ? new Date(`${config.dateFrom}T00:00:00`).toLocaleDateString('ko-KR') : ''} readOnly /><Input label="종료일" value={config.dateTo ? new Date(`${config.dateTo}T00:00:00`).toLocaleDateString('ko-KR') : ''} readOnly /></div><Input label="목표 건수" value={config.target_total ?? '제한 없음'} readOnly /><Input label="광고 제외어" value={config.adWords?.join(' · ') ?? ''} readOnly /><Input label="제외 출처" value={config.excludeSources?.join(' · ') ?? ''} readOnly /><Input label="제품명 필터" value={config.product_name_filter ? '사용' : '사용하지 않음'} readOnly />{Object.entries(config.perChannel ?? {}).filter(([channel])=>INTERNAL_TOOLS || channel !== 'fixture').map(([channel,limits])=><div key={channel}><h3 className="ds-t-label">{channelName(channel)}</h3><Input label="동시 수집 수" value={limits.concurrency} readOnly /><Input label="수집 간격(초)" value={limits.min_interval_s} readOnly /><Input label="키워드별 최대 수집 수" value={limits.max_per_keyword} readOnly /></div>)}</Card> : <Banner>저장된 수집 설정이 없습니다.</Banner>}</div>;
}

// Later-stage endpoints only read active data. Never mount their live editors in history mode.
export function VersionRouteBoundary({children}: {children: ReactNode}) {
  const pathname = usePathname(); const view = useVersion();
  const {sd} = useSessionStore();
  // Stage-eight Persona endpoints accept a version and provide their own readonly UI.
  const prep = sd?.prep as {derivedRef?: unknown} | undefined;
  if (pathname === '/pipeline/personas' && prep?.derivedRef) return children;
  const index = routes.indexOf(pathname.split('/').pop() ?? '');
  if (index < 3 || !view.meta) return children;
  const stage = `stage${index}` as Stage;
  return <div className="space-y-4"><VersionBanner stage={stage} />{view.readonly ? <><h1 className="ds-t-screen">{index}단계의 저장된 결과를 확인합니다</h1><Card><p>이 버전의 결과 파일과 저장 시각은 버전 비교에서 확인하세요.</p></Card></> : children}</div>;
}
