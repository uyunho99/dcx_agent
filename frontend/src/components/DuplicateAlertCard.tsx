"use client";

interface DuplicateAlertCardProps {
  keyword: string;
  existingCategory: string;
  onMove: () => void;
  onIgnore: () => void;
}

export default function DuplicateAlertCard({ keyword, existingCategory, onMove, onIgnore }: DuplicateAlertCardProps) {
  return (
    <div className="bg-amber-50/70 backdrop-blur-sm rounded-xl border border-amber-200/60 px-4 py-3 mt-2">
      <p className="text-amber-800 text-xs mb-2">
        &apos;{keyword}&apos;는 &apos;{existingCategory}&apos; 카테고리에 이미 있습니다. 이동하시겠습니까?
      </p>
      <div className="flex gap-2">
        <button
          onClick={onMove}
          className="px-3 py-1 rounded-lg text-xs font-medium bg-amber-500 text-white hover:bg-amber-600 transition-colors"
        >
          이동
        </button>
        <button
          onClick={onIgnore}
          className="px-3 py-1 rounded-lg text-xs font-medium bg-stone-200 text-stone-600 hover:bg-stone-300 transition-colors"
        >
          무시
        </button>
      </div>
    </div>
  );
}
