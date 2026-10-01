import { expect, it, vi } from 'vitest';

vi.mock('@/components/ds', () => ({}));

import { coverageInterpretation } from './CoveragePanel';

it.each([[], undefined])('explains unconnected coverage with humanQueries=%j', humanQueries => {
  expect(coverageInterpretation({ status: 'unconnected', humanQueries })).toBe(
    '검색광고가 연결되지 않아 사람 검색어를 받지 못했습니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.',
  );
});

it('preserves the missing-query interpretation for connected coverage', () => {
  expect(coverageInterpretation({ status: 'connected', missing_top: [['검색어', 100]] })).toBe(
    '누락 쿼리 1개가 다음 라운드의 입력에 반영됩니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.',
  );
});

it.each(['connected', 'failed', undefined])('preserves the zero-query interpretation for status=%s', status => {
  expect(coverageInterpretation({ status, humanQueries: [] })).toBe(
    '누락 쿼리 0개가 다음 라운드의 입력에 반영됩니다. 판정은 플래그만 하며 자동 탈락시키지 않습니다.',
  );
});
