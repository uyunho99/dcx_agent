"use client";
import { useState } from "react";
import type { Keyword } from "@/lib/types";
import DuplicateAlertCard from "./DuplicateAlertCard";
import SuggestedWordsPanel from "./SuggestedWordsPanel";

interface CategoryInputPanelProps {
  category: string;
  allKeywords: Keyword[];
  bk: string;
  problemDef: string;
  existingKeywords: string[];
  addedSuggestedWords: Set<string>;
  onManualAdd: (kw: string, cat: string) => void;
  onMove: (kwId: number | string, newCat: string) => void;
  onSuggestedAdd: (word: string, cat: string) => void;
  onSuggestedAddAll: (words: string[], cat: string) => void;
}

export default function CategoryInputPanel({
  category, allKeywords, bk, problemDef, existingKeywords,
  addedSuggestedWords, onManualAdd, onMove, onSuggestedAdd, onSuggestedAddAll,
}: CategoryInputPanelProps) {
  const [value, setValue] = useState("");
  const [duplicate, setDuplicate] = useState<{ kw: string; existingCat: string; existingId: number | string } | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const processInput = () => {
    if (!value.trim()) return;
    const words = value.split(",").map((w) => w.trim()).filter(Boolean);
    for (const word of words) {
      const existing = allKeywords.find((k) => k.kw.toLowerCase() === word.toLowerCase());
      if (existing) {
        if (existing.cat === category) {
          setToast("이미 존재하는 키워드입니다");
          setTimeout(() => setToast(null), 2000);
        } else {
          setDuplicate({ kw: word, existingCat: existing.cat, existingId: existing.id });
          return;
        }
      } else {
        onManualAdd(word, category);
      }
    }
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      processInput();
    }
  };

  const handleMoveKeyword = () => {
    if (duplicate) {
      onMove(duplicate.existingId, category);
      setDuplicate(null);
      setValue("");
    }
  };

  return (
    <div className="bg-stone-50/80 backdrop-blur-sm rounded-xl border border-stone-200/60 px-4 py-3 mt-2">
      {/* Manual input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="키워드 입력 (쉼표로 구분)"
          className="flex-1 px-3 py-1.5 rounded-lg text-xs border border-stone-200 bg-white/70 backdrop-blur-sm focus:outline-none focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
          autoFocus
        />
        <button
          onClick={processInput}
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-500 text-white hover:bg-indigo-600 transition-colors"
        >
          추가
        </button>
      </div>
      {toast && (
        <div className="text-amber-600 text-xs mt-1.5 px-1">{toast}</div>
      )}
      {duplicate && (
        <DuplicateAlertCard
          keyword={duplicate.kw}
          existingCategory={duplicate.existingCat}
          onMove={handleMoveKeyword}
          onIgnore={() => { setDuplicate(null); setValue(""); }}
        />
      )}

      {/* Divider */}
      <div className="border-t border-stone-200/60 my-3" />

      {/* Suggested words */}
      <SuggestedWordsPanel
        embedded
        category={category}
        bk={bk}
        problemDef={problemDef}
        existingKeywords={existingKeywords}
        addedWords={addedSuggestedWords}
        onAddWord={onSuggestedAdd}
        onAddAll={onSuggestedAddAll}
      />
    </div>
  );
}
