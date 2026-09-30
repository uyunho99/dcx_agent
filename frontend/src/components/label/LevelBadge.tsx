import { Badge } from '../ds/Badge';
import type { EvidenceLevel } from '@/lib/types';
export const levelNames: Record<EvidenceLevel, string> = {core:'Core',supporting:'Supporting',non:'Non'};
export function LevelBadge({level}: {level: EvidenceLevel}) {
 return <Badge tone={level === 'core' ? 'info' : 'neutral'}>{levelNames[level]}</Badge>;
}
