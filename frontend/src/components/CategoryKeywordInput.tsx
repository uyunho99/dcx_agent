"use client";
import { useState } from "react";
import type { Keyword } from "@/lib/types";
import DuplicateAlertCard from "./DuplicateAlertCard";

interface CategoryKeywordInputProps {
  category: string;
  allKeywords: Keyword[];
  onAdd: (kw: string, cat: string) => void;
  onMove: (kwId: number | string, newCat: string) => void;
}

export default function CategoryKeywordInput({ category, allKeywords, onAdd, onMove }: CategoryKeywordInputProps) {
  const [open, setOpen] = useState(false);
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
          return; // Stop processing, wait for user action
        }
      } else {
        onAdd(word, category);
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

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-indigo-600 hover:bg-indigo-50 transition-colors"
      >
        <span className="text-sm">+</span>
      </button>
    );
  }

  return (
    <div className="mt-2">
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
        <button
          onClick={() => { setOpen(false); setValue(""); setDuplicate(null); }}
          className="px-2 py-1.5 rounded-lg text-xs text-stone-400 hover:text-stone-600 transition-colors"
        >
          ✕
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
    </div>
  );
}
