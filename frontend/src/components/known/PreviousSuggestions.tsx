import type { InsightSuggestion } from '@/lib/types';
import { Button } from '../ds/Button';
export function PreviousSuggestions({items, disabled, onAdd}: {items: InsightSuggestion[]; disabled: boolean; onAdd: (item: InsightSuggestion) => void}) {
 return <details><summary>이전 세션 추천</summary><ul>{items.map(item => <li key={`${item.sessionId}:${item.insightId}`}><strong>{item.title}</strong><p>{item.painPoint}</p><Button size="sm" disabled={disabled} onClick={() => onAdd(item)}>추가</Button></li>)}</ul>{!items.length && <p>이전 세션 추천이 없습니다.</p>}</details>;
}
