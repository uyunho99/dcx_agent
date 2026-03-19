"use client";
import { useState } from "react";

interface NewCategoryInputProps {
  existingCategories: string[];
  onAdd: (name: string) => void;
}

export default function NewCategoryInput({ existingCategories, onAdd }: NewCategoryInputProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = () => {
    const name = value.trim();
    if (!name) return;
    if (existingCategories.some((c) => c.toLowerCase() === name.toLowerCase())) {
      setError("이미 존재하는 카테고리입니다");
      setTimeout(() => setError(null), 2000);
      return;
    }
    onAdd(name);
    setValue("");
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full py-3 rounded-xl text-sm font-medium border border-dashed border-stone-300 text-stone-500 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50/30 transition-all"
      >
        + 새 카테고리 추가
      </button>
    );
  }

  return (
    <div className="flex gap-2 items-center">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleSubmit(); } }}
        placeholder="카테고리명 입력"
        className="flex-1 px-3 py-2 rounded-lg text-sm border border-stone-200 bg-white/70 backdrop-blur-sm focus:outline-none focus:border-indigo-300 focus:ring-1 focus:ring-indigo-200"
        autoFocus
      />
      <button onClick={handleSubmit} className="px-4 py-2 rounded-lg text-sm font-medium bg-indigo-500 text-white hover:bg-indigo-600 transition-colors">
        생성
      </button>
      <button onClick={() => { setOpen(false); setValue(""); setError(null); }} className="px-2 py-2 rounded-lg text-sm text-stone-400 hover:text-stone-600 transition-colors">
        ✕
      </button>
      {error && <span className="text-amber-600 text-xs">{error}</span>}
    </div>
  );
}
