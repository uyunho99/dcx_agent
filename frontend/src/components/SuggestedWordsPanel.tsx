"use client";
import { useState } from "react";
import { suggestWords } from "@/lib/api";
import Spinner from "./Spinner";

interface SuggestedWordsPanelProps {
  category: string;
  bk: string;
  problemDef: string;
  existingKeywords: string[];
  addedWords: Set<string>;
  onAddWord: (word: string, category: string) => void;
  onAddAll: (words: string[], category: string) => void;
  embedded?: boolean;
}

interface WordItem {
  word: string;
  type: string;
}

export default function SuggestedWordsPanel({
  category, bk, problemDef, existingKeywords, addedWords, onAddWord, onAddAll, embedded,
}: SuggestedWordsPanelProps) {
  const [words, setWords] = useState<WordItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);

  const fetchSuggestions = async () => {
    setLoading(true);
    try {
      const res = await suggestWords({ bk, problemDef, category, existingKeywords });
      if (res.status === "ok" && res.words) {
        setWords(res.words);
        setFetched(true);
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  const adjectives = words.filter((w) => w.type === "형용사");
  const verbs = words.filter((w) => w.type === "동사");
  const remaining = words.filter((w) => !addedWords.has(w.word));

  return (
    <div className={embedded ? "" : "bg-violet-50/70 backdrop-blur-sm rounded-xl border border-violet-200/60 px-4 py-3 mt-2"}>
      {!fetched && !loading && (
        <button
          onClick={fetchSuggestions}
          className="text-xs font-medium text-violet-600 hover:text-violet-800 transition-colors"
        >
          추천 단어 불러오기
        </button>
      )}
      {loading && (
        <div className="flex items-center gap-2 text-violet-500 text-xs">
          <Spinner /> 추천 단어 생성 중...
        </div>
      )}
      {fetched && !loading && (
        <div>
          {adjectives.length > 0 && (
            <div className="mb-2">
              <span className="text-[10px] font-semibold text-violet-500 uppercase tracking-wider">형용사</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {adjectives.map((w) => (
                  <button
                    key={w.word}
                    onClick={() => onAddWord(w.word, category)}
                    disabled={addedWords.has(w.word)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                      addedWords.has(w.word)
                        ? "bg-stone-100 text-stone-400 opacity-50 cursor-not-allowed"
                        : "bg-violet-100/70 text-violet-700 hover:bg-violet-200 cursor-pointer"
                    }`}
                  >
                    {w.word}
                  </button>
                ))}
              </div>
            </div>
          )}
          {verbs.length > 0 && (
            <div className="mb-2">
              <span className="text-[10px] font-semibold text-violet-500 uppercase tracking-wider">동사</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {verbs.map((w) => (
                  <button
                    key={w.word}
                    onClick={() => onAddWord(w.word, category)}
                    disabled={addedWords.has(w.word)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                      addedWords.has(w.word)
                        ? "bg-stone-100 text-stone-400 opacity-50 cursor-not-allowed"
                        : "bg-violet-100/70 text-violet-700 hover:bg-violet-200 cursor-pointer"
                    }`}
                  >
                    {w.word}
                  </button>
                ))}
              </div>
            </div>
          )}
          {remaining.length > 0 && (
            <button
              onClick={() => onAddAll(remaining.map((w) => w.word), category)}
              className="mt-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-violet-500 text-white hover:bg-violet-600 transition-colors"
            >
              전체 추가 ({remaining.length}개)
            </button>
          )}
        </div>
      )}
    </div>
  );
}
