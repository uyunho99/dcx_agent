"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { generateKeywords, saveSession } from "@/lib/api";
import KeywordTag from "@/components/KeywordTag";
import Spinner from "@/components/Spinner";
import type { Keyword } from "@/lib/types";

const ROUND_NAMES: Record<string, string> = { r1: "R1: 발산", r2: "R2: 발산", r3: "R3: 수렴", "r3-expand": "R4: 재발산" };

export default function KeywordsPage() {
  const router = useRouter();
  const store = useSessionStore();
  const { sid, bk, pd, kw, ages, ar, gens, sd, pendingKw, lastRound } = store;

  const [newKw, setNewKw] = useState<Keyword[]>([]);
  const [rejected, setRejected] = useState<Set<number | string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [round, setRound] = useState(lastRound || sd?.step || "r1");
  const [isFinal, setIsFinal] = useState(false);

  const currentRound = round as string;

  const doGenerate = useCallback(async (rd: string) => {
    setLoading(true);
    setIsFinal(false);
    setRound(rd);
    try {
      const d = await generateKeywords({
        sid, bk, problemDef: pd,
        round: rd === "r1" ? 1 : rd === "r2" ? 2 : rd === "r3" ? 3 : 4,
        existingKeywords: kw.map((k) => k.kw), ages, ageRange: ar, gens,
      });
      const raw = (d.keywords || []) as unknown as Keyword[];
      const filtered = raw.filter((nk) => !kw.find((ek) => ek.kw === nk.kw));
      setNewKw(filtered);
      setRejected(new Set());
      store.setPendingKw(filtered, rd);
      if (sd) {
        const updated = { ...sd, step: rd, _pendingKw: filtered };
        store.setSession({ sd: updated, step: rd });
        await saveSession(sid!, updated);
      }
    } catch (e) {
      alert("키워드 생성 실패: " + (e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  }, [sid, bk, pd, kw, ages, ar, gens, sd, store]);

  useEffect(() => {
    if (pendingKw.length > 0 && lastRound) {
      setNewKw(pendingKw);
      setRound(lastRound);
    } else if (!loading && newKw.length === 0 && sid) {
      const step = sd?.step || "r1";
      if (step === "final") {
        setIsFinal(true);
      } else if (["r1", "r2", "r3", "r3-expand"].includes(step)) {
        doGenerate(step);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleKw = (id: number | string) => {
    setRejected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const approve = async () => {
    const approved = newKw.filter((k) => !rejected.has(k.id));
    store.addKeywords(approved);
    store.clearPendingKw();
    const allKw = [...kw, ...approved];
    const nextMap: Record<string, string> = { r1: "r2", r2: "r3", r3: allKw.length < 160 ? "r3-expand" : "final", "r3-expand": "final" };
    const next = nextMap[currentRound] || "final";
    if (next === "final") {
      setIsFinal(true);
      setNewKw([]);
      const updated = { ...sd!, allKw, step: "final", _pendingKw: [] };
      store.setSession({ sd: updated, step: "final", kw: allKw });
      await saveSession(sid!, updated);
    } else {
      const updated = { ...sd!, allKw, step: next, _pendingKw: [] };
      store.setSession({ sd: updated, step: next, kw: allKw });
      await saveSession(sid!, updated);
      doGenerate(next);
    }
  };

  const finalize = async () => {
    const kept = kw.filter((k) => !rejected.has(k.id));
    const updated = { ...sd!, allKw: kept, step: "crawl-setup" };
    store.setSession({ kw: kept, sd: updated, step: "crawl-setup" });
    await saveSession(sid!, updated);
    router.push("/pipeline/crawling");
  };

  // Final review mode
  if (isFinal) {
    const byCategory: Record<string, Keyword[]> = {};
    kw.forEach((k) => { if (!byCategory[k.cat]) byCategory[k.cat] = []; byCategory[k.cat].push(k); });

    return (
      <div>
        <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
          <h3 className="text-lg font-semibold text-stone-800 tracking-tight">최종 키워드 검토</h3>
          <p className="text-stone-500 text-sm mt-1">클릭하여 승인/거절. 거절한 키워드는 크롤링에서 제외됩니다</p>
        </div>
        <div className="bg-gradient-to-r from-indigo-50/70 to-violet-50/70 backdrop-blur-sm text-indigo-700 text-sm px-5 py-3 rounded-xl mb-5 font-medium border border-indigo-100">총 {kw.length}개</div>
        <div className="flex gap-3 mb-5">
          <button onClick={() => setRejected(new Set())} className="flex-1 py-2.5 rounded-xl text-sm font-medium border transition-colors bg-indigo-50 text-indigo-600 border-indigo-200 hover:bg-indigo-100">전체 승인</button>
          <button onClick={() => setRejected(new Set(kw.map((k) => k.id)))} className="flex-1 py-2.5 rounded-xl text-sm font-medium border transition-colors bg-rose-50 text-rose-600 border-rose-200 hover:bg-rose-100">전체 거절</button>
        </div>
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
          {Object.entries(byCategory).map(([cat, items]) => (
            <div key={cat} className="mb-4">
              <div className="text-sm font-semibold text-stone-700 mb-2">{cat} <span className="text-stone-400 font-normal ml-1">{items.length}</span></div>
              <div className="flex flex-wrap gap-2">
                {items.map((k) => (
                  <KeywordTag key={k.id} kw={k.kw} variant={rejected.has(k.id) ? "rejected" : "approved"} onClick={() => toggleKw(k.id)} />
                ))}
              </div>
            </div>
          ))}
        </div>
        <button onClick={() => { setIsFinal(false); doGenerate("r3-expand"); }} className="w-full bg-amber-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-amber-600 active:scale-[0.99] shadow-sm transition-all mb-3">키워드 더 생성</button>
        <button onClick={finalize} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all">확정 → 크롤링</button>
      </div>
    );
  }

  // Loading state
  if (loading) {
    return (
      <div>
        <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
          <h3 className="text-lg font-semibold text-stone-800 tracking-tight">{ROUND_NAMES[currentRound] || currentRound}</h3>
          <p className="text-stone-500 text-sm mt-1">{bk}</p>
        </div>
        <div className="flex items-center gap-2.5 text-stone-500 text-sm"><Spinner /> 키워드 생성 중...</div>
      </div>
    );
  }

  // Keyword review mode
  const byCategory: Record<string, { existing: Keyword[]; newItems: Keyword[] }> = {};
  kw.forEach((k) => { if (!byCategory[k.cat]) byCategory[k.cat] = { existing: [], newItems: [] }; byCategory[k.cat].existing.push(k); });
  newKw.forEach((k) => { if (!byCategory[k.cat]) byCategory[k.cat] = { existing: [], newItems: [] }; byCategory[k.cat].newItems.push(k); });

  return (
    <div>
      <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        <h3 className="text-lg font-semibold text-stone-800 tracking-tight">{ROUND_NAMES[currentRound] || currentRound}</h3>
        <p className="text-stone-500 text-sm mt-1">{bk}</p>
      </div>
      <div className="bg-gradient-to-r from-indigo-50/70 to-violet-50/70 backdrop-blur-sm text-indigo-700 text-sm px-5 py-3 rounded-xl mb-5 font-medium border border-indigo-100">
        누적: {kw.length}개 | 신규: {newKw.length}개
      </div>
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
        {Object.entries(byCategory).map(([cat, { existing, newItems }]) => (
          <div key={cat} className="mb-4">
            <div className="text-sm font-semibold text-stone-700 mb-2">{cat} <span className="text-stone-400 font-normal ml-1">{existing.length + newItems.length}</span></div>
            <div className="flex flex-wrap gap-2">
              {existing.map((k) => <KeywordTag key={k.id} kw={k.kw} variant="old" />)}
              {[...newItems].sort((a, b) => (b.score || 0) - (a.score || 0)).map((k) => (
                <KeywordTag key={k.id} kw={k.kw} score={k.score} variant={rejected.has(k.id) ? "rejected" : "new"} onClick={() => toggleKw(k.id)} />
              ))}
            </div>
          </div>
        ))}
      </div>
      <button onClick={approve} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all">승인 → 다음</button>
    </div>
  );
}
