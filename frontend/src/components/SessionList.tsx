"use client";
import { useEffect, useState } from "react";
import { listSessions, deleteSession } from "@/lib/api";

interface Props {
  onSelect: (sid: string) => void;
}

export default function SessionList({ onSelect }: Props) {
  const [sessions, setSessions] = useState<{ sid: string; bk: string; step: string }[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const d = await listSessions();
      setSessions(d.sessions || []);
    } catch {
      /* empty */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (sid: string) => {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    await deleteSession(sid);
    setSessions((s) => s.filter((x) => x.sid !== sid));
  };

  if (loading) return <div className="text-stone-400 text-sm p-3">로딩중...</div>;

  return (
    <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40 mb-5">
      <b className="text-base font-semibold text-stone-800">이어서 하기</b>
      {sessions.length === 0 ? (
        <p className="text-stone-400 text-sm mt-3">저장된 세션 없음</p>
      ) : (
        <div className="mt-3 space-y-1">
          {sessions.slice(0, 10).map((s) => (
            <div key={s.sid} className="flex items-center justify-between py-3 px-3 hover:bg-white/50 rounded-xl transition-colors">
              <div className="flex-1 cursor-pointer" onClick={() => onSelect(s.sid)}>
                <b className="text-sm font-semibold text-stone-800">{s.bk || "제목없음"}</b>
                <br />
                <small className="text-stone-400 text-xs">{s.step} | {s.sid}</small>
              </div>
              <button
                onClick={() => handleDelete(s.sid)}
                className="text-rose-500 text-xs px-3 py-1.5 rounded-lg hover:bg-rose-50 border border-rose-200 font-medium transition-colors"
              >
                삭제
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
