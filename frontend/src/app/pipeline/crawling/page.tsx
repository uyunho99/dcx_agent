'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { VersionStage, StageVersionAction } from "@/components/versions/StageVersion";
import { useVersion } from "@/components/versions/VersionProvider";
import { versionPath } from "@/lib/api/versions";
import { useSessionStore } from '@/stores/useSessionStore';
import { Badge, Banner, Button, Card, InsightCard, StatGrid } from '@/components/ds';
import { SaveBar } from '@/components/SaveBar';
import { Settings, channelNames } from '@/components/crawl/Settings';
import { GateTable } from '@/components/crawl/GateTable';
import { Progress } from '@/components/crawl/Progress';
import { contextRequest, patchSession } from '@/lib/api/context';
import { getCrawlConnections, getCrawlStatus, resumeCrawl, saveCrawlConfig, saveCrawlGate, startCrawlDetail, startCrawlList, stopCrawl, type CrawlConfig, type CrawlSession, type CrawlStatus, type Integration } from '@/lib/api/crawl';
import { displayError } from '@/lib/api/errors';
import { crawlNeedsSetup, crawlStartLabel, increasedResumeIntervals } from '@/lib/logic/finalFix';
import { approvedCrawlKeywords, deriveCrawlLoad } from '@/lib/logic/crawlConfig';
import { reconcileGateSelection, sameGateScope, type GateSelection } from '@/lib/logic/qaFix';
import { isDirty } from '@/lib/logic/isDirty';
import { INTERNAL_TOOLS } from '@/lib/internalTools';
import '@/components/crawl/crawl.css';

export default function CrawlingPage() {
  const {sid,sd}=useSessionStore(); const router=useRouter();
  if(!sid) return <Banner actions={<Button onClick={()=>router.push('/pipeline/start')}>프로젝트 선택하기</Button>}>프로젝트를 먼저 선택하세요.</Banner>;
  if(sd?.schemaVersion!==2) return <Banner tone="warning" actions={<Button onClick={()=>router.push('/pipeline/preprocess')}>전처리 화면으로</Button>}>구버전 세션은 0~2단계를 편집할 수 없습니다. 3단계 이후 화면에서 결과를 확인하세요.</Banner>;
  return <VersionStage stage="stage2"><CrawlScreen key={`${sid}:${String(sd.version??'')}`} sid={sid}/></VersionStage>;
}
function CrawlScreen({sid}:{sid:string}) {
  const { version, readonly, meta } = useVersion();
  const router=useRouter(); const context=useSessionStore(s=>s.projectContext);
  const [freshStarted,setFreshStarted]=useState(false);
  const [retry,setRetry]=useState(0);
  const [session,setSession]=useState<CrawlSession|null>(null);const [config,setConfig]=useState<CrawlConfig|null>(null);const [savedConfig,setSavedConfig]=useState<CrawlConfig|null>(null);const [draftConfig,setDraftConfig]=useState<CrawlConfig|null>(null);
  const [gateSelection,setGateSelection]=useState<GateSelection|null>(null);
  const excluded=gateSelection?.excluded??[];const savedGate=gateSelection?.saved??[];const draftGate=gateSelection?.draft??[];
  const setExcluded=(value:string[])=>setGateSelection(old=>old?{...old,excluded:value}:old);
  const setSavedGate=(value:string[])=>setGateSelection(old=>old?{...old,saved:value}:old);
  const setDraftGate=(value:string[])=>setGateSelection(old=>old?{...old,draft:value}:old);
  const [status,setStatus]=useState<CrawlStatus|null>(null);const [connections,setConnections]=useState<Integration[]>([]);const [busy,setBusy]=useState(false);const lock=useRef(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const [healthy,setHealthy]=useState(false);const [settings,setSettings]=useState(false);
  const generation=useRef(0);const alive=useRef(true);const latestStatus=useRef<CrawlStatus|null>(null);const [pollError,setPollError]=useState('');const hydrated=!!session;
  const refresh=useCallback(async()=>{
    const generationAtStart=generation.current;const next=await getCrawlStatus(sid);
    const changed=!latestStatus.current||!sameGateScope(latestStatus.current,next);
    // A new collection's saved exclusions must come from its current server session.
    const result=changed?await contextRequest<{data:CrawlSession}>(versionPath(`/session/${encodeURIComponent(sid)}`,version)):null;
    if(alive.current&&generationAtStart===generation.current){
      setGateSelection(old=>reconcileGateSelection(old,next,result?.data.crawlConfig?.gateExclusions??[],result?.data.drafts?.crawl?.gate));
      latestStatus.current=next;setStatus(next);setHealthy(true);setPollError('');
    }return next;
  },[sid,version]);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useEffect(()=>{
    if(!hydrated || readonly)return;
    let cancelled=false;let timer:ReturnType<typeof setTimeout>;
    const delay=()=>latestStatus.current?.status==='running'||latestStatus.current?.status==='stopping'?3000:10000;
    async function poll(){try{if(!lock.current)await refresh();}catch(e){if(!cancelled){setHealthy(false);setPollError(displayError(e, '수집 상태를 불러오지 못했습니다. 다시 확인하세요.'));}}if(!cancelled)timer=setTimeout(poll,delay());}
    timer=setTimeout(poll,delay());return()=>{cancelled=true;clearTimeout(timer);};
  },[refresh,hydrated,readonly]);
  useEffect(()=>{
    let cancelled=false;
    Promise.all([contextRequest<{data:CrawlSession}>(versionPath(`/session/${encodeURIComponent(sid)}`, version)),getCrawlConnections(),refresh()]).then(([result,integrations,initial])=>{
      if(cancelled)return;
      const loaded=deriveCrawlLoad(result,initial,context,INTERNAL_TOOLS);
      setSession(loaded.data);setConfig(loaded.config);setSavedConfig(loaded.savedConfig);setDraftConfig(loaded.config);setConnections(integrations);setError('');
    }).catch((e)=>{if(!cancelled)setError(displayError(e, '설정을 불러오지 못했습니다. 다시 확인하세요.'));});return()=>{cancelled=true;};
  },[sid,version,context,retry,refresh]);
  const running=status?.status==='running'||status?.status==='stopping';const disabled=busy||!!running||!healthy||!!session?.readonly;
  const freshSetup=!!session && crawlNeedsSetup(session, meta?.versions.find(v=>v.id===version)?.restartFrom) && !freshStarted;
  const gateView=!freshSetup&&!settings&&status?.kind==='list'&&status.status==='done'&&status.gate!==null;
  const setupView=freshSetup||settings||(!status?.kind&&!status?.report);
  const configChanged=isDirty(savedConfig,config);const gateChanged=isDirty([...savedGate].sort(),[...excluded].sort());
  const valid=!!config&&config.channels.length>0&&(!config.dateFrom||!config.dateTo||config.dateFrom<=config.dateTo)&&(config.target_total===null||Number.isInteger(config.target_total)&&config.target_total>0)&&Object.values(config.perChannel).every(v=>Number.isInteger(v.concurrency)&&v.concurrency>=1&&v.concurrency<=64&&v.min_interval_s>=0&&Number.isInteger(v.max_per_keyword)&&v.max_per_keyword>0)&&config.youtube.videos_per_keyword>=1&&Number.isInteger(config.youtube.videos_per_keyword)&&config.youtube.max_comments>=0&&Number.isInteger(config.youtube.max_comments);
  const keywords=approvedCrawlKeywords(session);const axes:Record<string,number>={};keywords.forEach(k=>{axes[k.axis]=(axes[k.axis]??0)+1;});
  const added=status?.added_keywords_count??0;
  async function action(fn:()=>Promise<void>,allowRunning=false){if(lock.current||(!allowRunning&&running)||session?.readonly)return;lock.current=true;generation.current++;setBusy(true);setHealthy(false);setError('');setNotice('');try{await fn();await refresh();}catch(e){setError(displayError(e, '요청에 실패했습니다. 입력값은 그대로 있습니다. 상태를 확인하고 다시 시도하세요.'));}finally{lock.current=false;setBusy(false);}}
  async function draft(){if(disabled)return;await action(async()=>{await patchSession(sid,{drafts:{crawl:gateView?{gate:{exclusions:excluded,collectionId:status!.collectionId,snapshot_id:status!.snapshot_id}}:{config}}}, version);if(gateView)setDraftGate([...excluded]);else setDraftConfig(config);setNotice('임시 저장했습니다. 저장하면 수집 설정에 반영합니다.');});}
  async function save(){if(disabled)return;await action(async()=>{if(gateView){await saveCrawlGate(sid,excluded,version);setSavedGate([...excluded]);setDraftGate([...excluded]);await patchSession(sid,{drafts:{crawl:{gate:null}}}, version);}else if(config&&valid){await saveCrawlConfig(sid,config,version);setSavedConfig(config);setDraftConfig(config);await patchSession(sid,{drafts:{crawl:{config:null}}}, version);}setNotice('저장했습니다. 수집 시작 버튼을 누르면 수집합니다.');});}
  const pausedChannels=status?.paused_channels ?? Object.entries(status?.channels??{}).filter(([,c])=>c.status.startsWith('paused')).map(([source])=>source);
  const paused=pausedChannels.length>0 || status?.status==='paused';
  return <div className="crawl-screen"><header><StageVersionAction stage="stage2" /><div className="ds-eyebrow">2단계 · 크롤링</div><h1 className={gateView?'ds-t-section':'ds-t-screen'}>{gateView?'본문 수집 전에 키워드를 정리합니다':setupView?`확정 키워드 ${keywords.length}개로 목록을 수집합니다`:status?.report?'수집 결과를 확인합니다':status?.kind==='list'?'채널별 글 목록을 수집합니다':'본문과 댓글을 수집합니다'}</h1>{setupView&&<p>먼저 채널별 글 목록(URL)만 모읍니다. 수집 효율을 확인한 뒤 본문·댓글 수집을 시작합니다. 검색어에는 제품명을 붙이지 않습니다.</p>}</header>
    {(error||pollError)&&<Banner tone="danger" actions={<Button onClick={()=>void action(async()=>{await refresh();if(!config)setRetry(v=>v+1);},true)}>다시 확인하기</Button>}>{error||pollError}</Banner>}{notice&&<Banner>{notice}</Banner>}
    {!config||!status?<p role="status">처리 중…</p>:<>
    {!freshSetup&&added>0&&<Banner actions={<Button disabled={disabled||configChanged} onClick={()=>void action(async()=>{await startCrawlList(sid,true,version);setSettings(false);})}>추가된 키워드만 수집</Button>}>기존 수집본 사용 중 · 추가된 키워드 {added}개</Banner>}
    {!freshSetup&&(status.status==='interrupted'||paused)&&<Banner tone="warning" actions={<><Button disabled={disabled} onClick={()=>void action(async()=>{await resumeCrawl(sid,version);setSettings(false);})}>이어서 진행</Button><Button disabled={disabled} onClick={()=>void action(async()=>{const min_interval_s=increasedResumeIntervals(pausedChannels,status,config);await resumeCrawl(sid,version,{min_interval_s});setSettings(false);})}>간격을 늘리고 재개</Button></>}>수집이 멈췄습니다. 완료된 결과는 저장되어 있습니다. 이어서 진행하세요. {status.stopReason === 'paused' ? '채널 차단 또는 파싱 오류로 멈췄습니다.' : ''}<div className="flex flex-wrap gap-2">{pausedChannels.filter(s=>INTERNAL_TOOLS||s!=='fixture').map(source=><Badge key={source}>{channelNames[source]??source}</Badge>)}</div><p>간격을 늘리면 멈춘 채널의 요청 간격을 두 배로 늘립니다(최소 1초).</p></Banner>}

    {setupView?<Settings config={config} onChange={setConfig} connections={connections} availableSources={status.available_sources} axes={axes} disabled={disabled}/>:gateView?<>
      <div className="crawl-columns"><InsightCard eyebrow="목록 신호" insight={`키워드 ${status.gate!.filter(r=>r.badges.length).length}개를 검토하세요`} interpretation={status.gate!.every(r=>r.listed===0)?'수집된 목록이 없습니다. 날짜 범위와 채널을 확인하고 목록을 다시 수집하세요.':'0건 · 저수율 · 고유 기여 낮음 배지를 확인하고 제외할 키워드를 선택하세요.'} evidence={[{label:'키워드',value:`${status.gate!.length}개`}]} nextAction={<Button disabled={disabled} onClick={()=>setSettings(true)}>설정으로 돌아가기</Button>}/><Card><h2 className="ds-t-card">상세 수집 예상</h2><StatGrid items={[{label:'대상 URL',value:status.estimate?.urls.toLocaleString()??'—'},{label:'예상 소요',value:status.estimate?`약 ${Math.ceil(status.estimate.minutes)}분`:'—'}]}/><p className="ds-t-caption">저장된 제외 목록 기준입니다. 중간에 멈춰도 이어서 진행합니다.</p></Card></div><GateTable rows={status.gate!} excluded={excluded} onChange={setExcluded} disabled={disabled}/>
    </>:<Progress status={status}/>}
    {!freshSetup&&INTERNAL_TOOLS&&status.snapshot_id&&<p className="ds-t-caption"><Badge>내부용</Badge> 스냅샷 {status.snapshot_id}</p>}
    {(setupView||gateView)&&<SaveBar dirty={gateView?isDirty(draftGate,excluded):isDirty(draftConfig,config)} valid={!disabled&&(gateView||valid)} saving={busy} onDraft={()=>void draft()} onSave={()=>void save()} primary={<Button variant="primary" disabled={disabled||(gateView?gateChanged||!status.snapshot_id:configChanged||!valid||keywords.length===0)} onClick={()=>void action(async()=>{if(gateView){if(gateChanged||!status.snapshot_id)return;await startCrawlDetail(sid,status.snapshot_id,version);}else{if(configChanged||!valid)return;await startCrawlList(sid,false,version);setFreshStarted(true);setExcluded([]);setSavedGate([]);setDraftGate([]);}setSettings(false);})}>{gateView?'상세 수집 시작':crawlStartLabel(freshSetup)}</Button>}/>}
    {(setupView||gateView)&&<p className="ds-t-caption">설정과 제외 선택을 저장한 다음 수집을 시작하세요.</p>}
    <div className="crawl-actions">{running&&<Button disabled={busy||!!session?.readonly} onClick={()=>void action(async()=>{await stopCrawl(sid,version);},true)}>일시 정지하기</Button>}{!freshSetup&&settings&&status.kind&&<Button onClick={()=>setSettings(false)}>수집 상태로 돌아가기</Button>}{!setupView&&status.report&&<Button variant="primary" onClick={()=>router.push('/pipeline/preprocess')}>전처리로 이동하기</Button>}</div>
    </>}
  </div>;
}
