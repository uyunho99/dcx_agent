"use client";
import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { startCrawl, getCrawlStatus, stopCrawl, saveSession } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import type { CrawlMode } from "@/lib/types";
import ProgressBar from "@/components/ProgressBar";
import Spinner from "@/components/Spinner";

export default function CrawlingPage() {
  const router = useRouter();
  const store = useSessionStore();
  const { sid, bk, kw, sd } = store;

  const [started, setStarted] = useState(sd?.step === "crawl-start");
  const [target, setTarget] = useState(50000);
  const [dateFrom, setDateFrom] = useState(new Date(Date.now() - 365 * 86400000).toISOString().split("T")[0]);
  const [dateTo, setDateTo] = useState(new Date().toISOString().split("T")[0]);
  const [cafes, setCafes] = useState("");
  const [excludeCafes, setExcludeCafes] = useState("");
  const [adFilter, setAdFilter] = useState("협찬,광고,제공받,원고료,체험단,서포터즈,중고,판매,거래");
  const [mode, setMode] = useState<CrawlMode>("api_only");
  const [cookies, setCookies] = useState("");

  const fetcher = useCallback(() => getCrawlStatus(sid!), [sid]);
  const shouldStop = useCallback((d: Awaited<ReturnType<typeof getCrawlStatus>>) => d.status === "done" || d.status === "error" || d.status === "stopped", []);
  const { data } = usePolling({ fetcher, interval: 3000, enabled: started && !!sid, shouldStop });

  const isDone = data?.status === "done" || data?.status === "stopped";
  const isStopped = data?.status === "stopped";
  const [stopping, setStopping] = useState(false);

  const handleStop = async () => {
    setStopping(true);
    await stopCrawl(sid!);
  };

  const handleStart = async () => {
    await startCrawl({
      sid, bk, keywords: kw.map((k) => k.kw), target, dateFrom, dateTo, cafes, excludeCafes, adFilter,
      mode, cookies: mode === "api_crawl4ai" ? cookies : undefined,
    });
    const updated = { ...sd!, step: "crawl-start" };
    store.setSession({ sd: updated, step: "crawl-start" });
    await saveSession(sid!, updated);
    setStarted(true);
  };

  const handleNext = async () => {
    const updated = { ...sd!, step: "preprocess-setup" };
    store.setSession({ sd: updated, step: "preprocess-setup" });
    await saveSession(sid!, updated);
    router.push("/pipeline/preprocess");
  };

  // --- Progress / Done view ---
  if (started) {
    const phase = data?.phase;
    const bodyCrawled = data?.body_crawled ?? 0;
    const bodyFailed = data?.body_failed ?? 0;
    const totalForBody = data?.total || 0;
    const bodyProgress = totalForBody > 0 ? ((bodyCrawled + bodyFailed) / totalForBody) * 100 : 0;
    const metaSummary = data?.meta_summary;

    return (
      <div>
        <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
          <h3 className="text-lg font-semibold text-stone-800 tracking-tight">크롤링 진행중</h3>
        </div>
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
          {data?.status === "error" ? (
            <div className="bg-red-50/70 backdrop-blur-sm text-red-700 text-sm px-4 py-3 rounded-xl font-medium border border-red-100">
              크롤링 오류: {data?.error || "알 수 없는 오류가 발생했습니다."}
            </div>
          ) : isStopped ? (
            <div className="bg-amber-50/70 backdrop-blur-sm text-amber-700 text-sm px-4 py-3 rounded-xl font-medium border border-amber-100">중지됨 — {(data?.total || 0).toLocaleString()}건 수집 완료</div>
          ) : isDone ? (
            <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl font-medium border border-indigo-100">완료! {(data?.total || 0).toLocaleString()}건</div>
          ) : (
            <div className="space-y-3">
              {/* Phase 1: API Collecting */}
              {phase === "api_collecting" && (
                <div className="flex items-center gap-2.5 text-sm text-amber-600 font-medium">
                  <Spinner size={16} /> 1단계: API 수집중... {(data?.total || 0).toLocaleString()}건
                </div>
              )}
              {/* Phase 2: Body Crawling */}
              {phase === "body_crawling" && (
                <>
                  <div className="text-sm text-emerald-600 font-medium">1단계: API 수집 완료 — {(data?.total || 0).toLocaleString()}건</div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2.5 text-sm text-amber-600 font-medium">
                      <Spinner size={16} /> 2단계: 본문 + 메타데이터 크롤링
                    </div>
                    <ProgressBar value={bodyProgress} />
                    <div className="flex gap-4 text-xs text-stone-500">
                      <span className="text-emerald-600">성공 {bodyCrawled.toLocaleString()}건</span>
                      <span className="text-red-500">실패 {bodyFailed.toLocaleString()}건</span>
                      <span>/ {totalForBody.toLocaleString()}건</span>
                    </div>
                  </div>
                </>
              )}
              {/* No phase (api_only mode) */}
              {!phase && (
                <div className="flex items-center gap-2.5 text-sm text-amber-600 font-medium">
                  <Spinner size={16} /> 진행중... {(data?.total || 0).toLocaleString()}건
                </div>
              )}
            </div>
          )}

          {/* --- Stop Button (visible during crawling) --- */}
          {!isDone && data?.status !== "error" && data?.status === "running" && (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="w-full bg-red-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-red-600 active:scale-[0.99] shadow-sm transition-all mt-4 disabled:opacity-50"
            >
              {stopping ? "중지 요청중..." : "크롤링 중지"}
            </button>
          )}

          {/* --- Done: Collection Stats Comparison (Crawl4AI mode) --- */}
          {isDone && data?.body_crawled != null && (
            <div className="mt-5 bg-stone-50/70 rounded-xl p-4 border border-stone-100">
              <b className="text-xs font-semibold text-stone-600">수집 통계</b>
              <div className="grid grid-cols-3 gap-3 mt-3">
                <div className="text-center p-3 bg-white rounded-lg border border-stone-100">
                  <div className="text-lg font-bold text-indigo-600">{(data.total || 0).toLocaleString()}</div>
                  <div className="text-[11px] text-stone-500 mt-0.5">API 수집</div>
                </div>
                <div className="text-center p-3 bg-white rounded-lg border border-stone-100">
                  <div className="text-lg font-bold text-emerald-600">{(data.body_crawled || 0).toLocaleString()}</div>
                  <div className="text-[11px] text-stone-500 mt-0.5">본문 성공</div>
                </div>
                <div className="text-center p-3 bg-white rounded-lg border border-stone-100">
                  <div className="text-lg font-bold text-red-500">{(data.body_failed || 0).toLocaleString()}</div>
                  <div className="text-[11px] text-stone-500 mt-0.5">본문 실패</div>
                </div>
              </div>
              {data.avg_body_length != null && (
                <div className="mt-3 text-xs text-stone-500">
                  평균 본문 길이: <b className="text-stone-700">{data.avg_body_length.toLocaleString()}자</b>
                  {data.body_crawled && data.total ? (
                    <span className="ml-2 text-emerald-600">({((data.body_crawled / data.total) * 100).toFixed(1)}% 성공률)</span>
                  ) : null}
                </div>
              )}
            </div>
          )}

          {/* --- Done: Metadata Summary (Crawl4AI mode) --- */}
          {isDone && metaSummary && (
            <div className="mt-4 bg-stone-50/70 rounded-xl p-4 border border-stone-100">
              <b className="text-xs font-semibold text-stone-600">메타데이터 요약</b>
              <div className="grid grid-cols-3 gap-3 mt-3">
                <div className="text-center p-3 bg-white rounded-lg border border-stone-100">
                  <div className="text-lg font-bold text-violet-600">{(metaSummary.avg_views ?? 0).toLocaleString()}</div>
                  <div className="text-[11px] text-stone-500 mt-0.5">평균 조회수</div>
                </div>
                <div className="text-center p-3 bg-white rounded-lg border border-stone-100">
                  <div className="text-lg font-bold text-violet-600">{(metaSummary.avg_comments ?? 0).toLocaleString()}</div>
                  <div className="text-[11px] text-stone-500 mt-0.5">평균 댓글</div>
                </div>
                <div className="text-center p-3 bg-white rounded-lg border border-stone-100">
                  <div className="text-lg font-bold text-violet-600">{(metaSummary.avg_likes ?? 0).toLocaleString()}</div>
                  <div className="text-[11px] text-stone-500 mt-0.5">평균 좋아요</div>
                </div>
              </div>
              <div className="mt-3 text-xs text-stone-500">유니크 작성자: <b className="text-stone-700">{(metaSummary.unique_authors ?? 0).toLocaleString()}명</b></div>
              {metaSummary.top_boards && metaSummary.top_boards.length > 0 && (
                <div className="mt-2">
                  <span className="text-xs text-stone-500">게시판 분포: </span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {metaSummary.top_boards.map((b) => (
                      <span key={b.board} className="px-2.5 py-1 bg-violet-50 rounded-full text-[11px] text-violet-600 font-medium">{b.board} <b>{b.count}</b></span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* --- Done: Cafe Stats (both modes) --- */}
          {isDone && data?.cafe_stats && data.cafe_stats.length > 0 && (
            <div className="mt-4">
              <b className="text-xs font-semibold text-stone-600">카페별 수집 현황</b>
              <div className="flex flex-wrap gap-2 mt-2">
                {data.cafe_stats.slice(0, 30).map((cs) => (
                  <span key={cs.cafe} className="px-3 py-1.5 bg-indigo-50 rounded-full text-xs text-indigo-600 font-medium">{cs.cafe} <b>{cs.count}</b></span>
                ))}
              </div>
            </div>
          )}
          {isDone && <button onClick={handleNext} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all mt-5">전처리 →</button>}
        </div>
      </div>
    );
  }

  // --- Setup form ---
  const kwByCategory: Record<string, number> = {};
  kw.forEach((k) => { kwByCategory[k.cat] = (kwByCategory[k.cat] || 0) + 1; });

  return (
    <div>
      <button onClick={() => router.push("/pipeline/keywords")} className="inline-flex items-center gap-1.5 text-stone-500 hover:text-stone-700 text-sm font-medium mb-4 transition-colors">← 키워드 검토로</button>
      <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        <h3 className="text-lg font-semibold text-stone-800 tracking-tight">크롤링 설정</h3>
      </div>
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl mb-4 font-medium border border-indigo-100"><b>{kw.length}</b> 키워드</div>
        <div className="space-y-4">

          {/* Mode Selection */}
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-2">수집 모드</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setMode("api_only")}
                className={`p-3 rounded-xl border text-left transition-all ${mode === "api_only" ? "border-indigo-300 bg-indigo-50/70 ring-1 ring-indigo-200" : "border-stone-200 bg-white/70 hover:border-stone-300"}`}
              >
                <div className="text-sm font-semibold text-stone-800">API-Only</div>
                <div className="text-[11px] text-stone-500 mt-0.5">빠름 · 제목+요약</div>
              </button>
              <button
                type="button"
                onClick={() => setMode("api_crawl4ai")}
                className={`p-3 rounded-xl border text-left transition-all ${mode === "api_crawl4ai" ? "border-indigo-300 bg-indigo-50/70 ring-1 ring-indigo-200" : "border-stone-200 bg-white/70 hover:border-stone-300"}`}
              >
                <div className="text-sm font-semibold text-stone-800">API + 본문 크롤링</div>
                <div className="text-[11px] text-stone-500 mt-0.5">정밀 · 본문+메타데이터</div>
              </button>
            </div>
          </div>

          {/* Cookie Input (Crawl4AI mode only) */}
          {mode === "api_crawl4ai" && (
            <div className="bg-amber-50/50 rounded-xl p-4 border border-amber-100">
              <label className="block text-sm font-medium text-stone-700 mb-1.5">네이버 로그인 쿠키 (선택)</label>
              <textarea
                className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400 font-mono"
                rows={2}
                placeholder="NID_AUT=xxx; NID_SES=yyy"
                value={cookies}
                onChange={(e) => setCookies(e.target.value)}
              />
              <p className="text-[11px] text-stone-500 mt-1.5">
                브라우저 개발자도구 → Application → Cookies에서 NID_AUT, NID_SES 값을 복사하세요.
              </p>
              {!cookies && (
                <p className="text-[11px] text-amber-600 mt-1">미입력 시 비로그인 크롤링 (일부 카페 본문 접근 제한 가능)</p>
              )}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">목표 건수</label>
            <input type="number" className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400" value={target} onChange={(e) => setTarget(Number(e.target.value))} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-sm font-medium text-stone-700 mb-1.5">시작일</label><input type="date" className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
            <div><label className="block text-sm font-medium text-stone-700 mb-1.5">종료일</label><input type="date" className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
          </div>
          <div><label className="block text-sm font-medium text-stone-700 mb-1.5">포함 카페</label><input className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400" placeholder="비우면 전체" value={cafes} onChange={(e) => setCafes(e.target.value)} /></div>
          <div><label className="block text-sm font-medium text-stone-700 mb-1.5">제외 카페</label><input className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400" placeholder="중고나라, 번개장터" value={excludeCafes} onChange={(e) => setExcludeCafes(e.target.value)} /></div>
          <div><label className="block text-sm font-medium text-stone-700 mb-1.5">광고 필터</label><textarea className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 placeholder:text-stone-400" rows={2} value={adFilter} onChange={(e) => setAdFilter(e.target.value)} /></div>
        </div>
        <div className="mt-4">
          <b className="text-xs font-semibold text-stone-600">키워드 빈도 (카테고리별)</b>
          <div className="flex flex-wrap gap-2 mt-2">
            {Object.entries(kwByCategory).sort((a, b) => b[1] - a[1]).map(([cat, cnt]) => (
              <span key={cat} className="px-3 py-1 bg-indigo-50 rounded-full text-xs font-medium text-indigo-600">{cat} <b>{cnt}</b></span>
            ))}
            <span className="px-3 py-1 bg-emerald-50 rounded-full text-xs font-semibold text-emerald-600">총 {kw.length}개</span>
          </div>
        </div>
        <button onClick={handleStart} className="w-full bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-indigo-600 active:scale-[0.99] shadow-sm transition-all mt-5">크롤링 시작</button>
      </div>
    </div>
  );
}
