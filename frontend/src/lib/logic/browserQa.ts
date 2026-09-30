/** Keep the backend identity: fake vectors can carry a Voyage model/dimension. */
export function embedderLabel(value: unknown): string {
 const metadata = value && typeof value === 'object' ? value as Record<string, unknown> : {};
 const name = typeof value === 'string' ? value : metadata.name;
 if (name === 'fake') return '가짜 임베더';
 if (name === 'voyage' || name === 'voyage-4' || (!name && metadata.model === 'voyage-4')) {
  return `${metadata.model ?? 'voyage-4'} · ${metadata.dim ?? 1024}`;
 }
 return typeof name === 'string' && name ? name : '확인 불가';
}
export function restartLabelNotice(session: {restartFrom?: unknown; parentVersion?: unknown} | null): string | null {
 return session?.restartFrom === 'stage4' && typeof session.parentVersion === 'string' && session.parentVersion
  ? `이 라벨은 ${session.parentVersion} 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다.` : null;
}
