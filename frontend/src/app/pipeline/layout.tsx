"use client";
import { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import { MessageCircle, Plug, X } from "lucide-react";
import { Badge, Button, Icon } from "@/components/ds";
import { INTERNAL_TOOLS } from "@/lib/internalTools";
import { InternalToolsProvider } from "@/lib/internalToolsContext";
import { IntegrationsDrawer } from "@/components/internal/IntegrationsDrawer";
import { useIntegrations } from "@/lib/api/integrations";
import { VersionProvider, VersionContent } from "@/components/versions/VersionProvider";
import { VersionRouteBoundary } from "@/components/versions/StageVersion";
import { VersionPicker } from "@/components/versions/VersionPicker";
import StepBar from "@/components/StepBar";
import ChatPanel from "@/components/ChatPanel";
import { useSessionStore } from "@/stores/useSessionStore";
import { sendChat } from "@/lib/api";
import { getPersistedSid, clearPersistedSid, restoreSessionToStore } from "@/lib/sessionPersist";

export default function PipelineLayout({ children }: { children: React.ReactNode }) {
  const [chatOpen, setChatOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const integrations = useIntegrations();
  const connectedCount = integrations.entries?.filter(entry => entry.connected).length;
  const store = useSessionStore();
  const { sid, bk, kw, step } = store;

  const [restoring, setRestoring] = useState(() => {
    if (typeof window === "undefined") return false;
    return !store.sid && !!getPersistedSid();
  });

  useEffect(() => {
    if (sid) return;
    const persisted = getPersistedSid();
    if (!persisted) return;

    setRestoring(true);
    restoreSessionToStore(persisted.sid, store)
      .catch(() => {
        clearPersistedSid();
      })
      .finally(() => setRestoring(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChat = useCallback(
    async (msg: string) => {
      const STEPS = ["시작", "키워드", "크롤링", "전처리", "라벨링", "학습", "클러스터링", "페르소나"];
      const stepIdx = ["start", "r1", "r2", "r3", "crawl-setup", "preprocess-setup", "labeling", "train-start", "clustering", "persona"].indexOf(step);
      const ctx = `제품:${bk || "미설정"}, 세션:${sid || "없음"}, 현재단계:${STEPS[Math.max(0, stepIdx)] || "시작"}, 키워드:${kw.length}개`;
      const d = await sendChat({ sid, query: msg, pipeline_context: ctx });
      return d.answer || "응답 없음";
    },
    [sid, bk, kw, step],
  );

  return (
    <VersionProvider><InternalToolsProvider value={{ drawerOpen, setDrawerOpen }}>
      <div className="pipeline-shell">
        <aside className="pipeline-side" aria-label="파이프라인">
          <Image className="pipeline-logo" src="/person-a-logo.png" alt="Person A" width={104} height={32} priority />
          <StepBar currentStep={step} />
          <div className="pipeline-foot">
            <div className="ds-t-label text-ink-strong">{bk || "세션 없음"}</div>
            <VersionPicker />
            <div className="pipeline-activity" data-slot="activity-badge" aria-live="polite" />
            {INTERNAL_TOOLS && <div className="pipeline-tools"><Button id="integrations-trigger" style={{ whiteSpace: "normal", height: "auto", minHeight: 28, textAlign: "left" }} variant="quiet" size="sm" aria-haspopup="dialog" aria-expanded={drawerOpen} onClick={() => setDrawerOpen(open => !open)}><Icon icon={Plug} />외부 API · {integrations.error ? "—" : connectedCount ?? "—"}/6 연결 열기</Button><Badge>내부용</Badge></div>}
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
          <div className="flex-1 min-h-0"><ChatPanel initialMessage="파이프라인 진행이나 결과에 대해 물어보세요." onSend={handleChat} /></div>
        </aside>}
      </div>
      {INTERNAL_TOOLS && drawerOpen && <IntegrationsDrawer {...integrations} returnFocusId="integrations-trigger" />}
    </InternalToolsProvider></VersionProvider>
  );
}
