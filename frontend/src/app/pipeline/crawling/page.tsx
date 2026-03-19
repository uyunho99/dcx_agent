"use client";
import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { startCrawl, getCrawlStatus, saveSession } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
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

  const fetcher = useCallback(() => getCrawlStatus(sid!), [sid]);
  const shouldStop = useCallback((d: Awaited<ReturnType<typeof getCrawlStatus>>) => d.status === "done" || d.status === "error", []);
  const { data } = usePolling({ fetcher, interval: 3000, enabled: started && !!sid, shouldStop });

  const isDone = data?.status === "done";

  const handleStart = async () => {
    await startCrawl({ sid, bk, keywords: kw.map((k) => k.kw), target, dateFrom, dateTo, cafes, excludeCafes, adFilter });
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

  if (started) {
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
          ) : isDone ? (
            <div className="bg-indigo-50/70 backdrop-blur-sm text-indigo-700 text-sm px-4 py-3 rounded-xl font-medium border border-indigo-100">완료! {(data?.total || 0).toLocaleString()}건</div>
          ) : (
            <div className="flex items-center gap-2.5 text-sm text-amber-600 font-medium"><Spinner size={16} /> 진행중... {(data?.total || 0).toLocaleString()}건</div>
          )}
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

  // Setup form
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
