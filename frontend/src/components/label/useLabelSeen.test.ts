import { expect, it, vi } from 'vitest';
const hooks = vi.hoisted(() => ({ ref: {current: new Set<string>()} }));
vi.mock('react', () => ({useRef: () => hooks.ref, useEffect: (effect: () => void) => effect()}));
vi.mock('@/lib/api/label', () => ({markLabelSeen: vi.fn().mockResolvedValue({})}));
import { markLabelSeen } from '@/lib/api/label';
import { useLabelSeen } from './useLabelSeen';
it('marks screen open once per sid/version, skipping readonly and polling replays', () => {
 hooks.ref.current.clear(); vi.mocked(markLabelSeen).mockClear();
 const onError = vi.fn();
 useLabelSeen('s', 'v1', true, onError);
 expect(markLabelSeen).not.toHaveBeenCalled();
 useLabelSeen('s', 'v1', false, onError);
 useLabelSeen('s', 'v1', false, onError);
 useLabelSeen('s', 'v2', false, onError);
 useLabelSeen('s2', 'v2', false, onError);
 expect(markLabelSeen).toHaveBeenCalledTimes(3);
 expect(markLabelSeen).toHaveBeenNthCalledWith(1, 's', 'v1');
});
