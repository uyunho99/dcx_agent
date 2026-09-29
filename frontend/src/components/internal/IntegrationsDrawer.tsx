"use client";

import { useEffect, useId, useRef } from "react";
import { Badge, Banner, Button, Skeleton } from "@/components/ds";
import { INTERNAL_TOOLS } from "@/lib/internalTools";
import { useInternalTools } from "@/lib/internalToolsContext";
import type { useIntegrations } from "@/lib/api/integrations";
import { nextTrapIndex } from "@/lib/logic/nextTrapIndex";

const names: Record<string, string> = {
  naver_shopping: "네이버 쇼핑", naver_search: "네이버 검색", naver_searchad: "네이버 검색광고",
  youtube: "YouTube", openai: "OpenAI", claude: "Claude",
};
const features: Record<string, string> = {
  category_suggest: "제품군 제안", crawl: "크롤링", coverage: "검색량 · 커버리지", llm: "언어 모델 분석",
};

type Props = ReturnType<typeof useIntegrations> & { returnFocusId: string };

export function IntegrationsDrawer(props: Props) {
  if (!INTERNAL_TOOLS) return null;
  return <DrawerContent {...props} />;
}

function DrawerContent({ entries, loading, error, recheck, returnFocusId }: Props) {
  const { setDrawerOpen } = useInternalTools();
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const panel = dialog.current;
    panel?.showModal();
    panel?.focus();
    return () => {
      panel?.close();
      document.getElementById(returnFocusId)?.focus();
    };
  }, [returnFocusId]);

  const retry = <Button size="sm" aria-disabled={loading} onClick={() => { if (!loading) void recheck(); }}>다시 확인하기</Button>;

  return <dialog ref={dialog} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
    className="integrations-drawer ds-t-body text-ink bg-paper border border-line rounded-overlay p-6"
    style={{ position: "fixed", inset: "0 0 0 auto", margin: 0, width: 360, maxWidth: "100vw", height: "100dvh", maxHeight: "100dvh", overflowY: "auto", boxShadow: "var(--shadow-overlay)" }}
    onCancel={event => { event.preventDefault(); setDrawerOpen(false); }}
    onKeyDown={event => {
      if (event.key !== "Tab") return;
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'))
        .filter(node => node.getClientRects().length > 0 && !node.closest("[inert]"));
      const next = nextTrapIndex(controls.length, controls.indexOf(document.activeElement as HTMLElement), event.shiftKey);
      event.preventDefault();
      (controls[next] ?? dialog.current)?.focus();
    }}>
    <div className="flex items-center justify-between gap-4 mb-4">
      <h2 id={titleId} className="ds-t-card text-ink-strong">외부 API</h2>
      <Badge>내부용</Badge>
      <Button variant="quiet" size="sm" onClick={() => setDrawerOpen(false)}>닫기</Button>
    </div>
    {loading && <div role="status" className="space-y-4 mb-4"><span>처리 중…</span><Skeleton height={72} /><Skeleton height={72} /></div>}
    {error && <Banner tone="danger" actions={retry}>외부 API 연결 상태를 불러오지 못했습니다. 다시 확인하세요.</Banner>}
    {!loading && !error && entries?.length === 0 && <Banner actions={retry}>외부 API 연결 정보가 없습니다. 다시 확인하세요.</Banner>}
    <ul className="space-y-4" aria-busy={loading}>
      {entries?.map(entry => <li key={entry.name} className="border border-line rounded-card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="ds-t-label text-ink-strong">{names[entry.name] ?? entry.name}</h3>
          <Badge tone={entry.connected ? "success" : "neutral"}>{entry.connected ? "연결됨" : "미연결"}</Badge>
        </div>
        <dl className="space-y-2">
          <div><dt className="ds-t-label">영향 받는 기능</dt><dd>{entry.affects.map(feature => features[feature] ?? feature).join(" · ") || "없음"}</dd></div>
          <div><dt className="ds-t-label">환경변수 이름</dt><dd className="ds-t-caption text-sub break-all">{entry.env_vars.join(" · ") || "없음"}</dd></div>
          {entry.last_error && <div className="text-danger"><dt className="ds-t-label">마지막 오류</dt><dd className="break-words">{entry.last_error}</dd></div>}
        </dl>
        <div className="flex justify-end">{retry}</div>
      </li>)}
    </ul>
    <style jsx>{`.integrations-drawer::backdrop { background: var(--ink); opacity: 0.3; }`}</style>
  </dialog>;
}
