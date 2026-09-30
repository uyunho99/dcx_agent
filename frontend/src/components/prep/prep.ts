import type { PrepConfig, PrepStatus } from '../../lib/types';

// Kept local to T17; these are the backend's boilerplate.v1.json defaults.
export const DEFAULT_BOILERPLATE: Record<string, string[]> = {
  naver_cafe: ['카페 회원이 되시면 전체 내용을 볼 수 있습니다.', '카페 가입하기'],
  naver_blog: ['공감', '이웃추가'], clien: [], ppomppu: [], youtube: [],
};
export const CHANNELS = [
  ['naver_cafe', '네이버 카페'], ['naver_blog', '네이버 블로그'],
  ['youtube', '유튜브'], ['ppomppu', '뽐뿌'], ['clien', '클리앙'],
] as const;
export type PrepSession = {
  labeling?: { started?: boolean };
  collectionId?: string | null;
  crawlConfig?: { adWords?: string[]; excludeSources?: string[] } | null;
  prep?: { config?: Partial<PrepConfig> };
  drafts?: { prep?: { config?: Partial<PrepConfig> } | null };
};
export type PrepReport = {
  original: number; after: number; removed: Record<string, number>;
  boilerplate_replaced: Record<string, number>; tokens_written: number;
  embedded: number; embed_failed_zero_vector: number;
  at?: string; embedder?: string; embedderName?: string; analyzer?: string; prepKey?: string;
};
export function prepEditLock(session: PrepSession): string | null {
  return session.labeling?.started ? '라벨링을 시작한 뒤에는 이 버전에서 바꿀 수 없습니다. 새 버전에서 다시 하세요.' : null;
}
export function prepConfig(session: PrepSession, includeDraft = true, serverConfig?: Partial<PrepConfig>): PrepConfig {
  const saved = session.prep?.config;
  const draft = includeDraft && !prepEditLock(session) ? session.drafts?.prep?.config : undefined;
  return {
    adFilter: session.crawlConfig?.adWords ?? [], excludeSources: session.crawlConfig?.excludeSources ?? [],
    minBodyChars: 10, analyzer: 'kiwi', tokenPos: ['NNG', 'NNP', 'VV', 'VA', 'XR'],
    embedder: serverConfig?.embedder ?? 'voyage', embedModel: serverConfig?.embedModel ?? 'voyage-4', embedDim: serverConfig?.embedDim ?? 1024,
    ...saved, ...draft,
    boilerplate: structuredClone({ ...DEFAULT_BOILERPLATE, ...saved?.boilerplate, ...draft?.boilerplate }),
  };
}
export function splitLines(value: string): string[] {
  return [...new Set(value.split(/\r?\n/).map(line => line.trim()).filter(Boolean))];
}
export function prepView(status: PrepStatus | null) {
  const raw = status?.status === 'done' ? status.stage3 : null;
  const report = raw && typeof raw.after === 'number'
    ? { ...raw, original: raw.original ?? 0, removed: raw.removed ?? {},
        boilerplate_replaced: raw.boilerplate_replaced ?? {}, tokens_written: raw.tokens_written ?? 0,
        embedded: raw.embedded ?? 0, embed_failed_zero_vector: raw.embed_failed_zero_vector ?? 0 } as PrepReport
    : null;
  return { report, empty: report?.after === 0, partial: (report?.embed_failed_zero_vector ?? 0) > 0,
    canNext: !!report && report.after > 0, running: status?.status === 'running',
    resumable: status?.status === 'interrupted',
  };
}
export function prepPhase(detail: Record<string, unknown> = {}): string {
  const phases: Record<string, string> = { filter: '필터', filtering: '필터', tokens: '토큰', tokenize: '토큰', embedding: '임베딩', embed: '임베딩' };
  return phases[String(detail.phase)] ?? ('total_shards' in detail ? '임베딩' : '필터 → 토큰 → 임베딩');
}
export function prepEstimate(report: Pick<PrepReport, 'original' | 'after'> | null) {
  return report ? { original: report.original, after: report.after, storageBytes: report.after * 1024 * 2 } : null;
}
