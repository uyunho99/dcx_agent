"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/useSessionStore";
import { generateKeywords, saveSession, scoreKeywords } from "@/lib/api";
import KeywordTag from "@/components/KeywordTag";
import Spinner from "@/components/Spinner";
import CategoryKeywordInput from "@/components/CategoryKeywordInput";
import NewCategoryInput from "@/components/NewCategoryInput";
import SuggestedWordsPanel from "@/components/SuggestedWordsPanel";
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

  // DnD state
  const [dragOverCat, setDragOverCat] = useState<string | null>(null);
  // Suggest panel state
  const [suggestingCat, setSuggestingCat] = useState<string | null>(null);
  // Track added suggested words
  const [addedSuggested, setAddedSuggested] = useState<Set<string>>(new Set());
  // Empty categories (user-created, no keywords yet)
  const [emptyCategories, setEmptyCategories] = useState<string[]>([]);

  const currentRound = round as string;
  const allKeywords = kw; // alias for clarity

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

  // === Shared handlers for manual input, DnD, suggestions ===

  const handleManualAdd = async (word: string, cat: string) => {
    const id = `m_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const keyword: Keyword = { id, kw: word, cat, manual: true };
    store.addManualKeyword(keyword);

    // Async scoring
    try {
      const res = await scoreKeywords({ bk, keywords: [{ kw: word, cat }] });
      if (res.status === "ok" && res.keywords?.[0]) {
        store.updateKeywordScore(id, res.keywords[0].score, res.keywords[0].total);
      }
    } catch {
      // scoring failure is non-critical
    }

    // Save session
    const currentKw = useSessionStore.getState().kw;
    if (sd) {
      const updated = { ...sd, allKw: currentKw };
      store.setSession({ sd: updated });
      await saveSession(sid!, updated);
    }
  };

  const handleMoveKeyword = (kwId: number | string, newCat: string) => {
    store.updateKeywordCategory(kwId, newCat);
    const currentKw = useSessionStore.getState().kw;
    if (sd) {
      const updated = { ...sd, allKw: currentKw };
      store.setSession({ sd: updated });
      saveSession(sid!, updated);
    }
  };

  const handleDrop = (e: React.DragEvent, targetCat: string) => {
    e.preventDefault();
    setDragOverCat(null);
    try {
      const data = JSON.parse(e.dataTransfer.getData("text/plain"));
      if (data.id !== undefined && data.fromCat !== targetCat) {
        // Check if it's a newKw item (review mode local state)
        const inNewKw = newKw.find((k) => k.id === data.id);
        if (inNewKw) {
          setNewKw((prev) => prev.map((k) => k.id === data.id ? { ...k, cat: targetCat } : k));
        } else {
          handleMoveKeyword(data.id, targetCat);
        }
      }
    } catch {
      // invalid drag data
    }
  };

  const handleDragOver = (e: React.DragEvent, cat: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverCat(cat);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    // Only clear highlight when actually leaving the drop zone, not when entering a child
    const related = e.relatedTarget as Node | null;
    if (!related || !e.currentTarget.contains(related)) {
      setDragOverCat(null);
    }
  };

  const handleSuggestedAdd = async (word: string, cat: string) => {
    const id = `s_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const keyword: Keyword = { id, kw: word, cat, manual: true };
    store.addManualKeyword(keyword);
    setAddedSuggested((prev) => new Set(prev).add(word));

    // No scoring for suggested words
    const currentKw = useSessionStore.getState().kw;
    if (sd) {
      const updated = { ...sd, allKw: currentKw };
      store.setSession({ sd: updated });
      await saveSession(sid!, updated);
    }
  };

  const handleSuggestedAddAll = async (words: string[], cat: string) => {
    const newKeywords: Keyword[] = words.map((word, i) => ({
      id: `s_${Date.now()}_${i}_${Math.random().toString(36).slice(2, 6)}`,
      kw: word, cat, manual: true,
    }));
    for (const keyword of newKeywords) {
      store.addManualKeyword(keyword);
    }
    setAddedSuggested((prev) => {
      const next = new Set(prev);
      words.forEach((w) => next.add(w));
      return next;
    });

    const currentKw = useSessionStore.getState().kw;
    if (sd) {
      const updated = { ...sd, allKw: currentKw };
      store.setSession({ sd: updated });
      await saveSession(sid!, updated);
    }
  };

  const handleNewCategory = (name: string) => {
    setEmptyCategories((prev) => [...prev, name]);
  };

  const handleDeleteEmptyCategory = (name: string) => {
    setEmptyCategories((prev) => prev.filter((c) => c !== name));
  };

  // === Helper to get variant for a keyword ===
  const getVariant = (k: Keyword, isRejected: boolean): "old" | "new" | "approved" | "rejected" | "manual" | "suggested" => {
    if (isRejected) return "rejected";
    if (k.manual && typeof k.id === "string" && k.id.startsWith("s_")) return "suggested";
    if (k.manual) return "manual";
    return "approved";
  };

  // === Render category section (shared between modes) ===
  const renderCategorySection = (
    cat: string,
    items: Keyword[],
    options: { showScores?: boolean; enableToggle?: boolean; isNewItems?: boolean }
  ) => {
    const { showScores, enableToggle, isNewItems } = options;
    return (
      <div
        key={cat}
        className={`mb-4 p-3 rounded-xl transition-all ${
          dragOverCat === cat ? "border-2 border-dashed border-indigo-300 bg-indigo-50/30" : "border-2 border-transparent"
        }`}
        onDragOver={(e) => handleDragOver(e, cat)}
        onDragLeave={handleDragLeave}
        onDrop={(e) => handleDrop(e, cat)}
      >
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-semibold text-stone-700">{cat}</span>
          <span className="text-stone-400 font-normal text-sm">{items.length}</span>
          <CategoryKeywordInput
            category={cat}
            allKeywords={allKeywords}
            onAdd={handleManualAdd}
            onMove={handleMoveKeyword}
          />
          <button
            onClick={() => setSuggestingCat(suggestingCat === cat ? null : cat)}
            className="px-2 py-1 rounded-lg text-xs font-medium text-violet-600 hover:bg-violet-50 transition-colors"
          >
            추천
          </button>
          {items.length === 0 && (
            <button
              onClick={() => handleDeleteEmptyCategory(cat)}
              className="px-2 py-1 rounded-lg text-xs text-stone-400 hover:text-rose-500 transition-colors"
            >
              삭제
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {(showScores ? [...items].sort((a, b) => (b.score || 0) - (a.score || 0)) : items).map((k) => {
            const isRejected = rejected.has(k.id);
            let variant: "old" | "new" | "approved" | "rejected" | "manual" | "suggested";
            if (isNewItems) {
              variant = isRejected ? "rejected" : "new";
            } else {
              variant = getVariant(k, isRejected);
            }
            return (
              <KeywordTag
                key={k.id}
                kw={k.kw}
                score={showScores ? k.score : undefined}
                variant={variant}
                onClick={enableToggle ? () => toggleKw(k.id) : undefined}
                draggable={true}
                kwId={k.id}
                cat={k.cat}
              />
            );
          })}
          {items.length === 0 && (
            <span className="text-xs text-stone-400 italic">비어있음 — 키워드를 추가하거나 드래그하세요</span>
          )}
        </div>
        {suggestingCat === cat && (
          <SuggestedWordsPanel
            category={cat}
            bk={bk}
            problemDef={pd}
            existingKeywords={items.map((k) => k.kw)}
            addedWords={addedSuggested}
            onAddWord={handleSuggestedAdd}
            onAddAll={handleSuggestedAddAll}
          />
        )}
      </div>
    );
  };

  // === Final review mode ===
  if (isFinal) {
    const byCategory: Record<string, Keyword[]> = {};
    kw.forEach((k) => { if (!byCategory[k.cat]) byCategory[k.cat] = []; byCategory[k.cat].push(k); });
    // Include empty user-created categories
    emptyCategories.forEach((c) => { if (!byCategory[c]) byCategory[c] = []; });

    const categories = Object.keys(byCategory);

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
          {Object.entries(byCategory).map(([cat, items]) =>
            renderCategorySection(cat, items, { enableToggle: true })
          )}
          <div className="mt-4">
            <NewCategoryInput existingCategories={categories} onAdd={handleNewCategory} />
          </div>
        </div>
        <button onClick={() => { setIsFinal(false); doGenerate("r3-expand"); }} className="w-full bg-amber-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-amber-600 active:scale-[0.99] shadow-sm transition-all mb-3">키워드 더 생성</button>
        <button onClick={finalize} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all">확정 → 크롤링</button>
      </div>
    );
  }

  // === Loading state ===
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

  // === Keyword review mode ===
  const byCategory: Record<string, { existing: Keyword[]; newItems: Keyword[] }> = {};
  kw.forEach((k) => { if (!byCategory[k.cat]) byCategory[k.cat] = { existing: [], newItems: [] }; byCategory[k.cat].existing.push(k); });
  newKw.forEach((k) => { if (!byCategory[k.cat]) byCategory[k.cat] = { existing: [], newItems: [] }; byCategory[k.cat].newItems.push(k); });
  // Include empty user-created categories
  emptyCategories.forEach((c) => { if (!byCategory[c]) byCategory[c] = { existing: [], newItems: [] }; });

  const reviewCategories = Object.keys(byCategory);

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
          <div
            key={cat}
            className={`mb-4 p-3 rounded-xl transition-all ${
              dragOverCat === cat ? "border-2 border-dashed border-indigo-300 bg-indigo-50/30" : "border-2 border-transparent"
            }`}
            onDragOver={(e) => handleDragOver(e, cat)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, cat)}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-semibold text-stone-700">{cat}</span>
              <span className="text-stone-400 font-normal text-sm">{existing.length + newItems.length}</span>
              <CategoryKeywordInput
                category={cat}
                allKeywords={[...allKeywords, ...newKw]}
                onAdd={handleManualAdd}
                onMove={handleMoveKeyword}
              />
              <button
                onClick={() => setSuggestingCat(suggestingCat === cat ? null : cat)}
                className="px-2 py-1 rounded-lg text-xs font-medium text-violet-600 hover:bg-violet-50 transition-colors"
              >
                추천
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {existing.map((k) => (
                <KeywordTag key={k.id} kw={k.kw} variant={k.manual ? "manual" : "old"} draggable={true} kwId={k.id} cat={k.cat} />
              ))}
              {[...newItems].sort((a, b) => (b.score || 0) - (a.score || 0)).map((k) => (
                <KeywordTag
                  key={k.id} kw={k.kw} score={k.score}
                  variant={rejected.has(k.id) ? "rejected" : "new"}
                  onClick={() => toggleKw(k.id)}
                  draggable={true} kwId={k.id} cat={k.cat}
                />
              ))}
            </div>
            {suggestingCat === cat && (
              <SuggestedWordsPanel
                category={cat}
                bk={bk}
                problemDef={pd}
                existingKeywords={[...existing, ...newItems].map((k) => k.kw)}
                addedWords={addedSuggested}
                onAddWord={handleSuggestedAdd}
                onAddAll={handleSuggestedAddAll}
              />
            )}
          </div>
        ))}
        <div className="mt-4">
          <NewCategoryInput existingCategories={reviewCategories} onAdd={handleNewCategory} />
        </div>
      </div>
      <button onClick={approve} className="w-full bg-emerald-500 text-white py-3 rounded-xl text-sm font-semibold hover:bg-emerald-600 active:scale-[0.99] shadow-sm transition-all">승인 → 다음</button>
    </div>
  );
}
