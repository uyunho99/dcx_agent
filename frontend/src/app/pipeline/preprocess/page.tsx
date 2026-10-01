'use client';
import { useRouter } from 'next/navigation';
import { Banner, Button } from '@/components/ds';
import { PrepScreen } from '@/components/prep/PrepScreen';
import { useVersion } from '@/components/versions/VersionProvider';
import { useSessionStore } from '@/stores/useSessionStore';

export default function PreprocessPage() {
  const sid = useSessionStore(state => state.sid);
  const schema = useSessionStore(state => state.sd?.schemaVersion);
  const { version } = useVersion();
  const router = useRouter();
  if (!sid) return <Banner actions={<Button onClick={() => router.push('/pipeline/start')}>프로젝트 선택하기</Button>}>프로젝트를 먼저 선택하세요.</Banner>;
  if (schema !== 2) return <Banner tone="warning" actions={<Button onClick={() => router.push('/pipeline/labeling')}>기존 결과 보기</Button>}>구버전 세션은 새 라벨링을 쓸 수 없습니다. 기존 결과만 볼 수 있습니다.</Banner>;
  return <PrepScreen key={`${sid}:${version ?? ''}`} sid={sid} />;
}
