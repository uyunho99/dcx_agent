export interface Keyword {
  id: number | string;
  kw: string;
  cat: string;
  score?: number;
  total?: number;
  manual?: boolean;
}

export interface SuggestedWord {
  word: string;
  type: "형용사" | "동사";
}

export interface SessionInfo {
  schemaVersion?: number;
  legacy?: boolean;
  updatedAt?: string;
  activity?: { kind: string; status: string; progress?: number; updatedAt?: string; label?: string } | null;
  sid: string;
  bk: string;
  step: string;
}

export interface SessionData {
  schemaVersion?: number;
  projectContext?: ProjectContext;
  drafts?: Record<string, unknown>;
  bk: string;
  problemDef: string;
  ages: string[];
  ageRange: string[];
  gens: string[];
  allKw: Keyword[];
  sid: string;
  step: string;
  labeledData?: LabeledItem[];
  _pendingKw?: Keyword[];
  [key: string]: unknown;
}

export interface LabeledItem {
  title: string;
  desc: string;
  cafe?: string;
  kw?: string;
  link?: string;
  label: number | string;
}

export interface CafeStats {
  cafe: string;
  count: number;
}

export interface ClusterInfo {
  id?: number;
  size: number;
  keywords: string[];
  keyword_counts?: Record<string, number>;
  samples: SampleDoc[];
  name?: string;
}

export interface SampleDoc {
  title: string;
  desc: string;
  cafe: string;
  kw?: string;
}

export interface Persona {
  name: string;
  situation: string;
  pain_point: string;
  insight: string;
}

export interface ClusterPersona {
  cluster_id: number;
  cluster_name: string;
  personas: Persona[];
}

export interface SNANode {
  id: string;
  name: string;
  type: "product" | "cluster" | "persona";
  size: number;
  pain_point?: string;
  insight?: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface SNALink {
  source: string | SNANode;
  target: string | SNANode;
  value: number;
}

export interface JobStatus {
  status: "running" | "done" | "error" | "not_found";
  progress?: number;
  phase?: string;
  error?: string;
  [key: string]: unknown;
}

export interface ProjectContext {
  schemaVersion: 1;
  bk: string;
  oneLiner: string;
  researchQuestion: { text: string; template?: string | null };
  projectType: { choice: string; note: string };
  analysisGoal: { choice: string; note: string };
  keyMetrics: string[];
  constraints: string[];
  positioning: { price: string; market: string };
  channels: string[];
  knownInsights: string[];
  productCategory: { l1: string; l2?: string | null; l3?: string | null; source: "shopping" | "llm_estimate" | "user" };
  targetScope?: { ageRanges: string[]; genders: string[]; households: string[]; lifeStages: string[]; note: string } | null;
  futureCustomer?: { choices: string[]; note: string } | null;
}

// Stage 3–5 wire contracts. Grades are calculated only by the rule API.
export type EvidenceLevel = 'core' | 'supporting' | 'non';
export type SemanticTag = 'sense' | 'feel' | 'think' | 'act' | 'relate' | 'outcome';
export type LabelTags = { anchor: boolean; sem: Record<SemanticTag, 0 | 1>; situation: boolean; reason_code?: 'ad' | 'no_needs' | 'pure_criticism' | 'other' | null; signal?: 'pain' | 'unmet' | 'workaround' | 'delight' | 'none' | null };
export type ReviewMode = 'escalate' | 'audit' | 'reissue';
export type WorkerState = 'none' | 'running' | 'paused' | 'failed' | 'interrupted' | 'done' | 'cancelled';
export type Worker = { runId: string; kind: string; state: WorkerState; progress: number; detail: Record<string, unknown>; reason?: string | null; error?: string | null };
export type LabelProgress = { state: string; pending: number; done?: number; bad?: number; progress?: number; reason?: string | null; runId?: string | null; estimate?: { seconds: number | null; [key: string]: unknown } };
export type KappaMetric = { n: number; accuracy: number | null; kappa: number | null };
export type KappaSummary = { n: number; fields: Record<string, KappaMetric>; grade: KappaMetric };
export type Overview = {
 started: boolean; mode: 'llm' | 'model'; modelId: string | null; progress: Record<string, LabelProgress>;
 definitionCheck: { needed: boolean; reason: string | null }; queue: { total: number; estimatedSeconds: number; byReason: Record<string, number> };
 now: { state: string; priority?: number; message?: string; action?: string | null }; merged: number; total: number; accepted: number; escalated: number; mismatchRate: number;
 levelDistribution: Record<EvidenceLevel, number>; audit: { round: number; n: number; kappaAI: KappaSummary; at: number | null }[];
 labelerAccuracy: { jev: KappaSummary; gpt: KappaSummary; n: number }; selfConsistency: KappaSummary & { accuracy: number | null; agree: number | null };
 changes: { judged: number; merged: number; accepted: number; queued: number }; lastSeenAt: string | null;
};
export type LegacyOverview = { legacy: true; readonly: true; message: string; legacyLabels: Record<string, unknown>[] };
export type SourceDocument = { doc_id: string; text?: string; title?: string; body?: string; content?: string; url?: string; channel?: string; comments?: { text: string }[] };
export type QueueItem = { doc_id: string; cursor?: string; reason?: 'labeler_failed' | 'grade_mismatch'; round?: number; document: SourceDocument | null };
export type LabelVote = { probs?: Record<string, number>; tags?: LabelTags; anchor?: boolean; sem?: LabelTags['sem']; situation?: boolean; evidence_level?: EvidenceLevel };
export type LabelSubmission = { doc_id: string; labeler: string; mode: ReviewMode; tags: LabelTags; round?: number; elapsedSeconds?: number };
export type LabelResult = { doc_id: string; level: EvidenceLevel; votes: Record<string, LabelVote> };
export type KnownInsight = { id: string; type: 'statement' | 'doc'; text: string; doc_id: string | null; from: 'stage0' | 'drawer' | 'rag' | 'prev_session'; createdAt: string; vectorRow: number | null; warning: string | null };
export type PrepConfig = { adFilter: string[]; excludeSources: string[]; minBodyChars: number; boilerplate: Record<string, string[]>; analyzer: 'kiwi'; tokenPos: string[]; embedder: 'voyage' | 'fake'; embedModel: 'voyage-4'; embedDim: 1024 };
export type PrepStatus = { status: WorkerState; progress: number; runId: string | null; detail?: Record<string, unknown>; derivedRef?: { collectionId: string; prepKey: string } | null; stage3?: Record<string, unknown> | null; error?: { kind: string; message: string } | null; reused?: boolean };
export type ModelMetadata = { modelId: string; selectable?: boolean; reason?: string | null; metrics?: Record<string, unknown>; [key: string]: unknown };
export type TrainingStatus = { readonly?: boolean; training: Record<string, unknown>; workers?: Worker[]; monitor?: (Partial<Worker> & { incomplete?: number }) | null; stage5?: Record<string, unknown> | null };
