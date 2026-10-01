"use client";
import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import Image from "next/image";
import { BookOpen, MessageCircle, Plug, X } from "lucide-react";
import { Badge, Button, Icon } from "@/components/ds";
import { INTERNAL_TOOLS } from "@/lib/internalTools";
import { InternalToolsProvider } from "@/lib/internalToolsContext";
import { IntegrationsDrawer } from "@/components/internal/IntegrationsDrawer";
import { useIntegrations } from "@/lib/api/integrations";
import { VersionProvider, VersionContent, useVersion } from "@/components/versions/VersionProvider";
import { VersionRouteBoundary } from "@/components/versions/StageVersion";
import { VersionPicker } from "@/components/versions/VersionPicker";
import { DirtyProvider } from "@/components/DirtyProvider";
import { SidebarActivity } from "@/components/SessionList";
import StepBar, { stepIndex } from "@/components/StepBar";
import { KnownInsightsDrawer } from "@/components/known/KnownInsightsDrawer";
import { getKnownInsights } from "@/lib/api/known";
import type { KnownInsight } from "@/lib/types";
import ChatPanel from "@/components/ChatPanel";
import { useSessionStore } from "@/stores/useSessionStore";
import { sendChat } from "@/lib/api";
import { getPersistedSid, clearPersistedSid, restoreSessionToStore } from "@/lib/sessionPersist";

export default function PipelineLayout({ children }: { children: React.ReactNode }) {
  const sid = useSessionStore(s => s.sid);
  return <DirtyProvider><VersionProvider><PipelineShell key={sid ?? "none"}>{children}</PipelineShell></VersionProvider></DirtyProvider>;
}

function PipelineShell({ children }: { children: React.ReactNode }) {
  const view = useVersion();
  const [chatOpen, setChatOpen] = useState(false);
  const [drawer, setDrawer] = useState<"known" | "integrations" | null>(null);
  const drawerOpen = drawer === "integrations";
  const setDrawerOpen: Dispatch<SetStateAction<boolean>> = useCallback(value => {
    setDrawer(current => (typeof value === "function" ? value(current === "integrations") : value) ? "integrations" : current === "integrations" ? null : current);
  }, []);
  const [known, setKnown] = useState<KnownInsight[] | null>(null);
  const [knownRevision, setKnownRevision] = useState(0);
  const integrations = useIntegrations();
  const connectedCount = integrations.entries?.filter(entry => entry.connected).length;
  const store = useSessionStore();
  const { sid, bk, kw, step } = store;

  const [restoring, setRestoring] = useState(true);
  const knownReadonly = view.readonly || view.loading || !!view.error;
  useEffect(() => {
    if (!sid) return;
    let active = true;
    getKnownInsights(sid, view.version).then(data => {if (active) setKnown(data.items);}).catch(() => {if (active) setKnown(null);});
    return () => {active = false;};
  }, [sid, view.version, knownRevision]);

  useEffect(() => {
    if (sid) { setRestoring(false); return; }
    const persisted = getPersistedSid();
    if (!persisted) { setRestoring(false); return; }

    setRestoring(true);
    restoreSessionToStore(persisted.sid, store)
      .catch(() => {
        clearPersistedSid();
      })
      .finally(() => setRestoring(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChat = useCallback(
    async (msg: string, novel: boolean) => {
      if (!sid) return "세션을 먼저 선택하세요.";
      const STEPS = ["시작", "키워드", "크롤링", "전처리", "라벨링", "학습", "클러스터링", "페르소나"];
      const stepIdx = stepIndex(step);
      const ctx = `제품:${bk || "미설정"}, 세션:${sid || "없음"}, 현재단계:${STEPS[Math.max(0, stepIdx)] || "시작"}, 키워드:${kw.length}개`;
      const d = await sendChat({ sid, query: msg, pipeline_context: ctx, novel });
      return d;
    },
    [sid, bk, kw, step],
  );

  return (
    <InternalToolsProvider value={{ drawerOpen, setDrawerOpen }}>
      <div className="pipeline-shell">
        <aside className="pipeline-side" aria-label="파이프라인">
          <Image className="pipeline-logo" src="/person-a-logo.png" alt="Person A" width={104} height={32} priority />
          <StepBar currentStep={step} session={view.session ?? (view.readonly ? null : store.sd)} />
          <div className="pipeline-foot">
            <div className="ds-t-label text-ink-strong">{bk || "세션 없음"}</div>
            <VersionPicker />
            <div className="pipeline-activity" data-slot="activity-badge" aria-live="polite"><SidebarActivity /></div>
            <Button id="known-insights-trigger" aria-label={`Known Insight · ${sid ? known?.length ?? "—" : 0}`} title="Known Insight" variant="quiet" size="sm" disabled={!sid || restoring} aria-haspopup="dialog" aria-expanded={drawer === "known"} onClick={() => setDrawer(current => current === "known" ? null : "known")}><Icon icon={BookOpen} /><span className="pipeline-foot-label">Known Insight · {sid ? known?.length ?? "—" : 0}</span></Button>
            {INTERNAL_TOOLS && <div className="pipeline-tools"><Button id="integrations-trigger" aria-label={`외부 API · ${integrations.error ? "—" : connectedCount ?? "—"}/${integrations.entries?.length ?? "—"} 연결 열기`} title={`외부 API · ${integrations.error ? "—" : connectedCount ?? "—"}/${integrations.entries?.length ?? "—"} 연결 열기`} style={{ whiteSpace: "normal", height: "auto", minHeight: 28, textAlign: "left" }} variant="quiet" size="sm" aria-haspopup="dialog" aria-expanded={drawerOpen} onClick={() => setDrawerOpen(open => !open)}><Icon icon={Plug} /><span className="pipeline-foot-label">외부 API · {integrations.error ? "—" : connectedCount ?? "—"}/{integrations.entries?.length ?? "—"} 연결 열기</span></Button><Badge>내부용</Badge></div>}
          </div>
        </aside>
        <div className="pipeline-content">
          <main className="pipeline-main">
            {restoring ? <div className="pipeline-loading" role="status">처리 중…</div> : <div className="pipeline-wrap"><VersionContent><VersionRouteBoundary>{children}</VersionRouteBoundary></VersionContent></div>}
          </main>
          {!chatOpen && <Button variant="quiet" className="pipeline-chat-open ds-btn-icon" onClick={() => setChatOpen(true)} aria-label="챗봇 열기" title="챗봇 열기"><Icon icon={MessageCircle} /></Button>}
        </div>
        {chatOpen && <aside className="pipeline-chat" aria-label="파이프라인 챗봇">
          <div className="pipeline-chat-header ds-t-label">
            <span>파이프라인 챗봇</span>
            <Button variant="quiet" size="sm" className="ds-btn-icon" onClick={() => setChatOpen(false)} aria-label="챗봇 닫기"><Icon icon={X} /></Button>
          </div>
          <div className="flex-1 min-h-0"><ChatPanel key={`${sid}:${view.version}`} sid={sid} version={view.version} readonly={knownReadonly} known={known ?? []} onKnownAdded={item => {setKnown(items => [...(items ?? []).filter(row => row.id !== item.id), item]);setKnownRevision(n => n + 1);}} initialMessage="파이프라인 진행이나 결과에 대해 물어보세요." onSend={handleChat} /></div>
        </aside>}
      </div>
      {sid && <KnownInsightsDrawer sid={sid} version={view.version} readonly={knownReadonly} open={drawer === "known"} onChange={items => {setKnown(items);setKnownRevision(n => n + 1);}} onClose={() => {setDrawer(null);setKnownRevision(n => n + 1);}} />}
      {INTERNAL_TOOLS && drawerOpen && <IntegrationsDrawer {...integrations} returnFocusId="integrations-trigger" />}
    </InternalToolsProvider>
  );
}
