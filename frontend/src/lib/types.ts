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

// Stage 8 contracts (task-T12-brief.md). `run` is a generation; `runId` is a worker.
export type PersonaGrade = 'observed' | 'inferred' | 'speculated';
export type PersonaGradeLabel =
  | { text: '관측'; shape: 'circle' }
  | { text: '추론'; shape: 'triangle' }
  | { text: '추측'; shape: 'cross' }
  | { text: '근거 부족'; shape: null };
export type PersonaZone = 'A' | 'B' | 'C' | 'D' | 'E' | 'F';
export type PersonaState = WorkerState | 'pending' | 'stale';
export type PersonaErrorKind = 'evidence_required' | 'running' | 'locked' | 'not_ready' | 'stale_run';
export type PersonaRunRequest = { fresh?: boolean; personas?: string[] };
export type PersonaRunResponse = { runId: string };
export type PersonaRetryRequest = { run: string };
export type PersonaStatus = {
  status: PersonaState; run: string | null; progress: number;
  personas: { id: string; status: PersonaState; error: unknown | null }[];
  stage8?: Record<string, unknown> | null;
};
export type PersonaField = { text: string; cite: string[] };
export type PersonaConstraint = { constraint: string; verdict: 'ok' | 'violates' | 'review'; reason: string };
export type PersonaPrescription = {
  direction: string; target_metric: string; contribution: string; journey_hypothesis: string;
  constraint: PersonaConstraint[]; blocked: boolean; represcribed: boolean;
};
export type PersonaScope = { verdict: 'in' | 'outside'; reason: string };
// Nested card/trace serialization is not specified by the API table. Keep those
// payloads open instead of asserting a router-specific layout before T11 lands.
export type PersonaCard = {
  status: PersonaState; card: Record<string, unknown> | null;
  grades?: Record<string, Record<string, PersonaGrade | null>>;
  trace?: Record<string, unknown>[]; prescription?: PersonaPrescription | null;
  constraint?: PersonaConstraint[]; scope?: PersonaScope | null; error?: unknown;
  [key: string]: unknown;
};
export type PersonaCardsResponse = { run: string | null; personas: Record<string, PersonaCard>; package_run?: string };
export type PersonaMapPoint = {
  context_id: string; persona_id: string; cluster_id: string;
  i: number; s: number; odi: number; zone: PersonaZone; star: boolean; counter: boolean;
  shape: string; tone: string | number;
};
export type PersonaMap = {
  points: PersonaMapPoint[];
  base: { s_line: number; diag1: [[number, number], [number, number]]; diag2: [[number, number], [number, number]] };
  legend: unknown;
};
// The tree's node/link envelope is deliberately opaque in the published contract.
export type PersonaTree = Record<string, unknown>;
export type PersonaContextRow = PersonaMapPoint & { name?: string; persona_name?: string };
export type PersonaSortDirection = 'asc' | 'desc';

export type InsightErrorKind = 'persona_required' | 'not_found';
export type InsightRunRequest = { mode: 'derive' | 'concept'; target?: string };
export type InsightRunResponse = { runId: string };
export type InsightTarget = 'insights' | `concept:${string}`;
export type InsightChatRequest = { target: InsightTarget; message: string };
export type InsightChatResponse =
  | { ok: true; revision: number }
  | { ok: false; message: '요청을 반영하지 못했습니다. 다르게 말해 주세요.' };
export type InsightRevertRequest = { target: InsightTarget; revision: number };
export type InsightRevertResponse = { revision: number };
export type InsightConfirmRequest = { ids: string[] };
export type InsightConfirmResponse = { confirmed: string[] };
export type InsightItem = { id: string; title: string; pain_point: string; context_ids: string[]; known_ki_id: string | null };
export type InsightCxDimension = '정신적' | '물리적' | '문화적' | '시스템';
export type InsightJourneyRow = {
  context_id: string; action: string; feeling: string; service: string; service_action: string; cx_4d: InsightCxDimension;
};
export type InsightConcept = {
  persona_profile: unknown; basis: string; pain_points: Record<string, unknown>[];
  journey: InsightJourneyRow[]; constraint_check: PersonaConstraint[];
  [key: string]: unknown;
};
// The brief fixes the revision envelope, but not history entry or metric layout.
export type InsightRevision<T> = { revision: number; items: T[]; history: Record<string, unknown>[] };
export type InsightBars = { bars: unknown; mean: number | null; targets: string[] };
export type InsightRadar = Record<string, unknown>;
export type InsightResponse = {
  insights: InsightRevision<InsightItem>; concepts: InsightRevision<InsightConcept>;
  bars: InsightBars | null; radar: InsightRadar | null;
};
export type InsightSuggestion = { sessionId: string; insightId: string; title: string; painPoint: string };
export type InsightSuggestionsResponse = { items: InsightSuggestion[] };
export type InsightSuggestedKnownRequest = { type: 'statement'; text: string };
