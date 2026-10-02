'use client';
import { useSessionStore } from '@/stores/useSessionStore';
import { useVersion } from '@/components/versions/VersionProvider';
import { EvidenceScreen } from '@/components/evidence/EvidenceScreen';
export default function EvidencePage() {
  const {sid,sd} = useSessionStore();
  const view = useVersion();
  const prep = sd?.prep as {derivedRef?:unknown} | undefined;
  if(sid && prep?.derivedRef) return <EvidenceScreen key={`${sid}:${view.version ?? ''}`} sid={sid} version={view.version} readonly={view.readonly || !!view.conflict}/>;
  return <div className="ds-card"><p>옛 세션 · 읽기 전용</p><p>근거 탐색은 새 전처리 결과가 있는 세션에서 열립니다.</p></div>;
}
