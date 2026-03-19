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
  sid: string;
  bk: string;
  step: string;
}

export interface SessionData {
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
