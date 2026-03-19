const API = process.env.NEXT_PUBLIC_API_URL || "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return res.json();
}

// Sessions
export const listSessions = () => request<{ status: string; sessions: { sid: string; bk: string; step: string }[] }>("/sessions");
export const getSession = (sid: string) => request<{ status: string; data: Record<string, unknown> }>(`/session/${sid}`);
export const saveSession = (sid: string, data: Record<string, unknown>) =>
  request("/save-session", { method: "POST", body: JSON.stringify({ sid, data }) });
export const deleteSession = (sid: string) => request(`/delete-session/${sid}`, { method: "DELETE" });

// Keywords
export const generateKeywords = (body: Record<string, unknown>) =>
  request<{ status: string; keywords: Record<string, unknown>[]; round: number }>("/generate-keywords", { method: "POST", body: JSON.stringify(body) });

// Crawling
export const startCrawl = (body: Record<string, unknown>) =>
  request("/crawl", { method: "POST", body: JSON.stringify(body) });
export const getCrawlStatus = (sid: string) =>
  request<{ status: string; total: number; cafe_stats: { cafe: string; count: number }[]; error?: string }>(`/status/${sid}`);

// Preprocessing
export const startPreprocess = (body: Record<string, unknown>) =>
  request("/preprocess", { method: "POST", body: JSON.stringify(body) });
export const getPreprocessStatus = (sid: string) =>
  request<{ status: string; original?: number; filtered?: number }>(`/preprocess-status/${sid}`);

// Labeling
export const getSample = (sid: string, percent = 2) =>
  request<{ status: string; samples: Record<string, unknown>[]; total: number }>(`/sample/${sid}?percent=${percent}`);

// Training
export const startTrain = (body: Record<string, unknown>) =>
  request("/train", { method: "POST", body: JSON.stringify(body) });
export const getTrainStatus = (sid: string) =>
  request<Record<string, unknown>>(`/train-status/${sid}`);

// Clustering
export const startCluster = (body: Record<string, unknown>) =>
  request("/cluster", { method: "POST", body: JSON.stringify(body) });
export const getClusterStatus = (sid: string) =>
  request<Record<string, unknown>>(`/cluster-status/${sid}`);
export const clusterRefine = (body: Record<string, unknown>) =>
  request("/cluster-refine", { method: "POST", body: JSON.stringify(body) });

// Embedding
export const startEmbed = (body: Record<string, unknown>) =>
  request("/embed", { method: "POST", body: JSON.stringify(body) });
export const getEmbedStatus = (sid: string) =>
  request<Record<string, unknown>>(`/embed-status/${sid}`);

// Persona
export const startPersona = (body: Record<string, unknown>) =>
  request("/persona", { method: "POST", body: JSON.stringify(body) });
export const getPersonaStatus = (sid: string) =>
  request<Record<string, unknown>>(`/persona-status/${sid}`);

// SNA
export const getSNAData = (sid: string) =>
  request<{ status: string; nodes: Record<string, unknown>[]; links: Record<string, unknown>[]; bk: string }>(`/sna-data/${sid}`);

// Chat
export const sendChat = (body: Record<string, unknown>) =>
  request<{ status: string; answer: string; sources: Record<string, unknown>[]; added_keywords?: string[] }>("/chat", { method: "POST", body: JSON.stringify(body) });
export const sendInsightChat = (body: Record<string, unknown>) =>
  request<{ status: string; answer: string; modified: boolean; sources: Record<string, unknown>[] }>("/insight-chat", { method: "POST", body: JSON.stringify(body) });
