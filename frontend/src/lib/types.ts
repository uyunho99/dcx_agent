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
export type LabelProgress = { state: string; pending: number; total?: number; done?: number; bad?: number; progress?: number; reason?: string | null; runId?: string | null; estimate?: { seconds: number | null; [key: string]: unknown } };
export type KappaMetric = { n: number; accuracy: number | null; kappa: number | null };
export type KappaSummary = { n: number; fields: Record<string, KappaMetric>; grade: KappaMetric };
export type Overview = {
 started: boolean; mode: 'llm' | 'model'; modelId: string | null; progress: Record<string, LabelProgress>;
 definitionCheck: { needed: boolean; reason: string | null }; queue: { total: number; estimatedSeconds: number; byReason: Record<string, number> };
 now: { state: string; priority?: number; message?: string; action?: string | null }; merged: number; total: number; accepted: number; trainable?: number; escalated: number; mismatchRate: number;
 levelDistribution: Record<EvidenceLevel, number>; audit: { round: number; n: number; kappaAI: KappaSummary; at: number | null }[];
 labelerAccuracy: { jev: KappaSummary; gpt: KappaSummary; n: number }; selfConsistency: KappaSummary & { accuracy: number | null; agree: number | null };
 changes: { judged: number; merged: number; accepted: number; queued: number }; lastSeenAt: string | null;
};
export type LegacyOverview = { legacy: true; readonly: true; message: string; legacyLabels: Record<string, unknown>[] };
export type SourceDocument = { doc_id: string; text?: string; title?: string; body?: string; content?: string; url?: string; channel?: string; comments?: { text: string }[] };
export type QueueItem = { doc_id: string; cursor?: string; reason?: 'labeler_failed' | 'grade_mismatch' | 'model_uncertain' | 'model_disagree'; round?: number; document: SourceDocument | null };
export type LabelVote = { probs?: Record<string, number>; tags?: LabelTags; anchor?: boolean; sem?: LabelTags['sem']; situation?: boolean; evidence_level?: EvidenceLevel };
export type LabelSubmission = { doc_id: string; labeler: string; mode: ReviewMode; tags: LabelTags; round?: number; elapsedSeconds?: number };
export type LabelResult = { doc_id: string; level: EvidenceLevel; votes: Record<string, LabelVote> };
export type KnownInsight = { id: string; type: 'statement' | 'doc'; text: string; doc_id: string | null; from: 'stage0' | 'drawer' | 'rag' | 'prev_session'; createdAt: string; vectorRow: number | null; warning: string | null };
export type PrepConfig = { adFilter: string[]; excludeSources: string[]; minBodyChars: number; boilerplate: Record<string, string[]>; analyzer: 'kiwi'; tokenPos: string[]; embedder: 'voyage' | 'fake'; embedModel: 'voyage-4'; embedDim: 1024 };
export type PrepStatus = { config?: PrepConfig; status: WorkerState; progress: number; runId: string | null; detail?: Record<string, unknown>; derivedRef?: { collectionId: string; prepKey: string } | null; stage3?: Record<string, unknown> | null; error?: { kind: string; message: string } | null; reused?: boolean };
export type ModelMetadata = { modelId: string; selectable?: boolean; reason?: string | null; metrics?: Record<string, unknown>; [key: string]: unknown };
export type TrainingStatus = { readonly?: boolean; training: Record<string, unknown>; workers?: Worker[]; monitor?: (Partial<Worker> & { incomplete?: number }) | null; stage5?: Record<string, unknown> | null };

export type Coverage = {
  previous?: Pick<Coverage, 'source' | 'weighting' | 'humanQueries' | 'm1' | 'm2' | 'm2_bands' | 'm6' | 'm7' | 'm7_reason' | 'missing_top'>;
  status?: string;
  source?: 'searchad' | 'autocomplete';
  weighting?: 'volume' | 'rank';
  seeds?: number;
  failedSeeds?: number;
  startedAt?: string;
  humanQueries?: [string, number][];
  m1?: number | null;
  m2?: (number | null)[] | null;
  m2_bands?: { label: string; value: number | null }[];
  m6?: number | null;
  m7?: number | null;
  m7_reason?: string | null;
  missing_top?: [string, number][];
};

// Stage 6 wire contracts. `run` is the result generation, not the worker runId.
export type SegmentLayer = 'clusters' | 'personas' | 'contexts';
export type SegmentQuality = { cohesion?: number | null; boundary?: number | null; ari?: number | null; npmi?: number | null; flags?: string[] };
export type SegmentRepresentative = { docId: string; text: string; source: string; field: string; idx: number | null };
export type SegmentRequest = { layer: 'clusters'; id: string; kind: 'split' | 'merge'; note: string };
export type SegmentRequestMemo = SegmentRequest & { at: string };
export type SegmentRow = { id: string; docs: number; nameDraft: string | null; name: string | null; confirmed: boolean };
export type SegmentCluster = SegmentRow & {
  keywords: string[]; reps: SegmentRepresentative[]; quality: SegmentQuality;
  channels: Record<string, number>; channelSkew: boolean; requests: SegmentRequestMemo[];
};
export type SegmentPersona = SegmentRow & {
  clusterId: string; authors: number; desireDraft: string | null; desire: string | null;
  goalsDraft: string[]; goals: string[]; centrality: [string, number][];
  network: { nodes: { id: string; persona: number; score: number }[]; edges: { source: string; target: string; weight: number }[] };
  similar: { id: string; score: number; desire: string }[]; reps: SegmentRepresentative[]; flags: string[];
};
export type SegmentContext = SegmentRow & {
  personaId: string; actionDraft: string | null; action: string | null; keywords: string[];
  dominantConstraint: string | null; dimsSummary: Record<string, unknown>; quality: SegmentQuality; flags: string[];
};
export type SegmentKSuggest = { k: number; suggested: number; silhouette: Record<string, number>; inertia: Record<string, number>; dendrogram: unknown[]; sample: number };
export type SegmentStatus = {
    detail?: { step?: string; persona?: number; personas?: number; docs?: number; total?: number };
  run: string | null; status: WorkerState | 'review'; step: 'load' | 'L1' | 'L2' | 'L3' | 'quality' | 'dims' | 'drafts';
  progress: number; confirm: Record<SegmentLayer, string>; stage6?: Record<string, unknown>; reason?: string;
};
export type SegmentClustersResponse = { run: string | null; clusters: SegmentCluster[]; kSuggest: SegmentKSuggest | null };
export type SegmentPersonasResponse = { run: string | null; personas: SegmentPersona[] };
export type SegmentContextsResponse = { run: string | null; contexts: SegmentContext[]; emptyGoalConstraintRatio: number };
export type SegmentRunRequest = { k?: number; confirmReset?: boolean };
export type SegmentConfirmation = { run: string; name: string; confirm: true };
export type SegmentPersonaConfirmation = SegmentConfirmation & { desire: string; goals: [string] | [string, string] | [string, string, string] };
export type SegmentContextConfirmation = SegmentConfirmation & { action: string };
export type SegmentBulkConfirmation = { run: string; contexts: { id: string; name: string; action: string }[] };
export type SegmentBulkResponse = { run: string; contexts: SegmentContext[] };
export type SegmentBand = 'core' | 'fringe' | 'edge';
export type SegmentDocsOptions = { context?: string; band?: SegmentBand; offset?: number; limit?: number };
export type SegmentDocument = {
  docId: string; title: string; body: string; comments: unknown[]; url: string;
  clusterId: string | null; personaId: string | null; contextId: string | null;
  theta: number | null; thetaJson: number[] | null; distCentroid: number | null; band: SegmentBand | null;
  comboRarity: number | null; emerging: number | null; lexicalSurprise: number | null;
  sentiment: number | null; predEntropy: number | null; evidenceLevel: EvidenceLevel | null;
  source: string | null; authorHash: string | null; date: string | null;
};
export type SegmentDocsResponse = { run: string | null; docs: SegmentDocument[]; total: number; offset: number; limit: number };
export type SegmentDraft = { run: string; [key: string]: unknown };
export type SegmentErrorKind = 'locked' | 'confirm_required' | 'stale_run' | 'validation';
