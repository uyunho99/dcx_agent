"use client";
import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Badge, Banner, Button, Card, Skeleton } from "@/components/ds";
import { contextSessions } from "@/lib/api/context";
import { usePolling } from "@/lib/usePolling";
import { INTERNAL_TOOLS } from "@/lib/internalTools";
import { useSessionStore } from "@/stores/useSessionStore";
import type { SessionInfo } from "@/lib/types";

function activityLabel(activity: SessionInfo["activity"]) {
  if (!activity) return "검토 대기";
  const {status, kind, progress} = activity;
  if (status === "interrupted") return "중단됨 · 이어서 진행";
  if ((status === "paused_blocked" || status === "blocked")) return "차단으로 멈춤";
  if (status === "failed" || status === "error") return "실패 · 다시 진행";
  if (status === "done" || status === "completed") return "완료";
  if (status !== "running") return "검토 대기";
  if (kind.startsWith("keyword_round_")) return `R${kind.split("_").pop()} 생성 중`;
  return `${kind.includes("list") ? "목록" : "상세"} 수집${typeof progress === "number" ? ` ${Math.round(progress)}%` : " 중"}`;
}
export default function SessionList({ onSelect }: {onSelect: (sid: string, session?: SessionInfo) => void}) {
  const [error, setError] = useState(false);
  const [slot, setSlot] = useState<Element | null>(null);
  const sid = useSessionStore(state => state.sid);
  const fetcher = useCallback(async () => {
    try { const result = await contextSessions(); setError(false); return result.sessions; }
    catch (error) { setError(true); throw error; }
  }, []);
  const {data, refresh} = usePolling({ fetcher, interval: 10000, enabled: true });
  useEffect(() => { const timer = setTimeout(() => setSlot(document.querySelector('[data-slot="activity-badge"]')), 0); return () => clearTimeout(timer); }, []);
  const current = data?.find(session => session.sid === sid);
  return <Card>
    <h2 className="ds-t-card">최근 세션</h2>
    {slot && current && createPortal(<Badge>{activityLabel(current.activity)}</Badge>, slot)}
    {error && <Banner tone="danger" actions={<Button onClick={refresh}>새로고침하기</Button>}>세션 목록을 불러오지 못했습니다. 새로고침하세요.</Banner>}
    {!data && !error && <div role="status" className="space-y-3"><span>처리 중…</span>{[0,1,2].map(i => <Skeleton key={i} />)}</div>}
    {data?.length === 0 && <p className="ds-t-body">아직 프로젝트가 없습니다. 아래에서 새 프로젝트를 설정하세요.</p>}
    {data?.map(session => <div key={session.sid} className="flex flex-wrap items-center justify-between gap-3 py-3 border-b border-line">
      <div><Button variant="quiet" onClick={() => onSelect(session.sid, session)}>{session.bk || "제목 없는 프로젝트"} 열기</Button>
        <div className="ds-t-caption">{session.updatedAt && new Date(session.updatedAt).toLocaleDateString("ko-KR")}{INTERNAL_TOOLS && ` · ${session.sid}`}</div>
      </div>
      <div className="flex gap-2">{session.legacy && <Badge>구버전</Badge>}<Badge tone={["interrupted", "paused_blocked", "blocked", "failed"].includes(session.activity?.status ?? "") ? "warning" : "neutral"}>{activityLabel(session.activity)}</Badge></div>
    </div>)}
    <p className="ds-t-caption mt-3">주의가 필요한 세션이 위에 옵니다. 구버전 세션은 0~2단계를 편집할 수 없습니다.</p>
  </Card>;
}
