"use client";
import { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { useSessionStore } from "@/stores/useSessionStore";
import { listSessions, getSession, getPersonaStatus, getClusterStatus, getSNAData } from "@/lib/api";
import PersonaCard from "@/components/PersonaCard";
import Spinner from "@/components/Spinner";
import type { ClusterPersona, SNANode, SNALink } from "@/lib/types";

const SNAGraph = dynamic(() => import("@/components/SNAGraph"), { ssr: false });

export default function InsightsPage() {
  const store = useSessionStore();
  const { sid, bk } = store;

  const [sessions, setSessions] = useState<{ sid: string; bk: string; step: string }[]>([]);
  const [personas, setPersonas] = useState<ClusterPersona[]>([]);
  const [clusterData, setClusterData] = useState<Record<string, { size: number; keywords: string[]; samples: { title: string; desc: string; cafe: string; kw?: string }[] }>>({});
  const [snaNodes, setSnaNodes] = useState<SNANode[]>([]);
  const [snaLinks, setSnaLinks] = useState<SNALink[]>([]);
  const [showSNA, setShowSNA] = useState(false);
  const [snaLoaded, setSnaLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<"done" | "cluster-only" | "in-progress" | "none">("none");

  useEffect(() => {
    listSessions().then((d) => setSessions(d.sessions || []));
  }, []);

  const loadInsights = useCallback(async (targetSid: string) => {
    setLoading(true);
    setPersonas([]);
    setClusterData({});
    setSnaNodes([]);
    setSnaLinks([]);
    setShowSNA(false);
    setSnaLoaded(false);
    setPipelineStatus("none");

    try {
      // Load session
      const resp = await getSession(targetSid);
      const d = (resp.data || resp) as Record<string, unknown>;
      store.setSession({
        sid: targetSid, bk: (d.bk as string) || "", pd: (d.problemDef as string) || "",
        kw: (d.allKw as never[]) || [], sd: d as never,
        ages: (d.ages as string[]) || [], ar: (d.ageRange as string[]) || [], gens: (d.gens as string[]) || [],
      });

      // Load persona status
      const pResp = await getPersonaStatus(targetSid);
      if (pResp.status === "done") {
        setPersonas((pResp.personas as ClusterPersona[]) || []);
        setPipelineStatus("done");

        // Load clusters for enrichment
        try {
          const cResp = await getClusterStatus(targetSid);
          if ((cResp as Record<string, unknown>).clusters) {
            setClusterData((cResp as Record<string, unknown>).clusters as typeof clusterData);
          }
        } catch { /* cluster data is optional enrichment */ }

        // Load SNA data
        try {
          const sResp = await getSNAData(targetSid);
          if (sResp.status === "ok") {
            setSnaNodes(sResp.nodes as unknown as SNANode[]);
            setSnaLinks(sResp.links as unknown as SNALink[]);
            setSnaLoaded(true);
          }
        } catch { /* SNA is optional */ }
      } else {
        // Fallback: check cluster status
        try {
          const cResp = await getClusterStatus(targetSid);
          if ((cResp as Record<string, unknown>).status === "done") {
            setClusterData(((cResp as Record<string, unknown>).clusters as typeof clusterData) || {});
            setPipelineStatus("cluster-only");
          } else {
            setPipelineStatus("in-progress");
          }
        } catch {
          setPipelineStatus("in-progress");
        }
      }
    } catch {
      setPipelineStatus("none");
    } finally {
      setLoading(false);
    }
  }, [store]);

  useEffect(() => {
    if (sid) loadInsights(sid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectSession = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val) loadInsights(val);
  };

  const toggleSNA = () => {
    setShowSNA((v) => !v);
  };

  return (
    <div className="space-y-5">
      {/* Header + Session selector */}
      <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
        <b className="text-base font-semibold text-stone-800">인사이트 분석</b>
        <div className="mt-3">
          <select
            className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-sm bg-white/70 focus:ring-2 focus:ring-indigo-100 focus:border-indigo-300 transition-colors"
            value={sid || ""}
            onChange={handleSelectSession}
          >
            <option value="">세션을 선택하세요...</option>
            {sessions.filter((s) => s.bk).map((s) => (
              <option key={s.sid} value={s.sid}>{s.bk} ({s.sid})</option>
            ))}
          </select>
        </div>
        {sid && snaLoaded && (
          <div className="mt-3">
            <button
              onClick={toggleSNA}
              className="px-4 py-2 bg-indigo-500 text-white text-sm font-medium rounded-full hover:bg-indigo-600 transition-colors shadow-sm"
            >
              SNA 시각화 {showSNA ? "숨기기" : "보기"}
            </button>
          </div>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-2.5 text-stone-500 text-sm">
          <Spinner size={16} /> 로딩중...
        </div>
      )}

      {/* Empty state */}
      {!sid && !loading && (
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
          <p className="text-stone-500 text-sm">세션을 선택하면 분석 결과가 표시됩니다.</p>
        </div>
      )}

      {/* SNA Graph */}
      {showSNA && snaNodes.length > 0 && (
        <div className="bg-white rounded-2xl p-5 shadow-[0_4px_12px_rgba(0,0,0,0.06)] border border-white/40">
          <b className="text-base font-semibold text-stone-800">페르소나 네트워크</b>
          <div className="flex gap-4 text-xs text-stone-500 mt-2 mb-3">
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#6366f1]" /> 제품
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#f59e0b]" /> 클러스터
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#10b981]" /> 페르소나
            </span>
          </div>
          <SNAGraph nodes={snaNodes} links={snaLinks} />
        </div>
      )}

      {/* Persona Results (pipeline done) */}
      {pipelineStatus === "done" && personas.length > 0 && (
        <div className="space-y-5">
          <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
            <b className="text-base font-semibold text-stone-800">페르소나 분석 결과</b>
            <span className="text-stone-400 text-sm ml-2">{bk}</span>
          </div>

          {personas.map((cl, ci) => {
            const cInfo = clusterData[String(ci)] || clusterData[String(cl.cluster_id)] || { size: 0, keywords: [], samples: [] };
            const topKw = (cInfo.keywords || []).slice(0, 6);

            return (
              <div key={cl.cluster_id} className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
                {/* Cluster header */}
                <div className="flex items-center gap-2 mb-3">
                  <b className="text-indigo-600 font-semibold">{cl.cluster_name || `클러스터 ${cl.cluster_id}`}</b>
                  <span className="text-stone-400 text-xs">{cInfo.size || 0}건</span>
                </div>

                {/* Top keywords */}
                {topKw.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-4">
                    {topKw.map((k) => (
                      <span key={k} className="px-2.5 py-1 bg-indigo-50/80 backdrop-blur-sm rounded-full text-xs text-indigo-600 font-medium border border-indigo-100/50">
                        {k}
                      </span>
                    ))}
                  </div>
                )}

                {/* Persona cards grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {cl.personas.map((p, i) => <PersonaCard key={i} persona={p} />)}
                </div>

                {/* Full keywords */}
                {cInfo.keywords && cInfo.keywords.length > 0 && (
                  <div className="mt-5 pt-4 border-t border-stone-100/60">
                    <b className="text-xs font-semibold text-stone-500">주요 키워드</b>
                    <div className="flex flex-wrap gap-2 mt-2">
                      {cInfo.keywords.map((k) => (
                        <span key={k} className="px-2.5 py-1 bg-indigo-50/80 backdrop-blur-sm rounded-full text-xs text-indigo-600 font-medium border border-indigo-100/50">
                          {k}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Evidence samples */}
                {cInfo.samples && cInfo.samples.length > 0 && (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-indigo-500 text-xs font-medium hover:text-indigo-600 transition-colors">
                      ▼ 근거 원문 ({cInfo.samples.length}건)
                    </summary>
                    <div className="mt-3 space-y-2">
                      {cInfo.samples.map((s, i) => (
                        <div key={i} className="bg-stone-50/80 backdrop-blur-sm rounded-xl p-3.5 text-sm leading-relaxed border border-stone-100/50">
                          <b className="text-stone-700">[{s.kw}]</b>{" "}
                          <span className="font-medium text-stone-700">{s.title}</span>
                          <p className="text-stone-500 mt-1 text-[13px] line-clamp-3">{s.desc}</p>
                          <span className="text-stone-400 text-xs">{s.cafe}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            );
          })}

          <div className="bg-gradient-to-r from-indigo-50/70 to-violet-50/70 backdrop-blur-sm text-indigo-700 text-sm px-5 py-3 rounded-xl font-medium border border-indigo-100/50">
            인사이트 챗봇으로 더 깊이 분석하세요!
          </div>
        </div>
      )}

      {/* Cluster-only fallback (persona not done yet) */}
      {pipelineStatus === "cluster-only" && Object.keys(clusterData).length > 0 && (
        <div className="space-y-5">
          <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
            <b className="text-base font-semibold text-stone-800">클러스터 결과</b>
            <span className="text-stone-400 text-sm ml-2">{bk}</span>
          </div>

          {Object.entries(clusterData).map(([cid, cInfo]) => (
            <div key={cid} className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
              <div className="flex items-center gap-2 mb-3">
                <b className="text-indigo-600 font-semibold">클러스터 {Number(cid) + 1}</b>
                <span className="text-stone-400 text-xs">{cInfo.size || 0}건</span>
              </div>

              {cInfo.keywords && cInfo.keywords.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-3">
                  {cInfo.keywords.map((k) => (
                    <span key={k} className="px-2.5 py-1 bg-indigo-50/80 backdrop-blur-sm rounded-full text-xs text-indigo-600 font-medium border border-indigo-100/50">
                      {k}
                    </span>
                  ))}
                </div>
              )}

              {cInfo.samples && cInfo.samples.length > 0 && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-indigo-500 text-xs font-medium hover:text-indigo-600 transition-colors">
                    원문 샘플 ({cInfo.samples.length}건)
                  </summary>
                  <div className="mt-2 space-y-2">
                    {cInfo.samples.map((s, i) => (
                      <div key={i} className="bg-stone-50/80 backdrop-blur-sm rounded-xl p-3 text-sm leading-relaxed border border-stone-100/50">
                        <b className="text-stone-700">[{s.kw}]</b> {s.title}
                        <p className="text-stone-500 mt-1 text-xs line-clamp-2">{s.desc}</p>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          ))}

          <div className="bg-amber-50/70 backdrop-blur-sm text-amber-700 text-sm px-5 py-3 rounded-xl font-medium border border-amber-100/50">
            페르소나 도출을 완료하면 더 자세한 인사이트를 볼 수 있습니다.
          </div>
        </div>
      )}

      {/* In-progress state */}
      {pipelineStatus === "in-progress" && !loading && (
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] border border-white/40">
          <p className="text-stone-500 text-sm">파이프라인 진행중입니다. 완료 후 결과가 여기 표시됩니다.</p>
        </div>
      )}
    </div>
  );
}
