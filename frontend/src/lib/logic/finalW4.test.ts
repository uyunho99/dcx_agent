import { expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { increasedResumeIntervals } from './finalFix';
import { limits } from './crawlConfig';

it('uses effective Naver defaults', () => {
  for (const source of ['naver_blog', 'naver_cafe']) {
    expect(limits(source).concurrency).toBe(1);
    expect(limits(source).min_interval_s).toBe(1);
  }
});
it('renders channel status from availability and keyless Naver copy', () => {
  const settings = readFileSync('src/components/crawl/Settings.tsx', 'utf8');
  expect(settings).toContain("available ? '사용 가능'");
  expect(settings).toContain('검색 결과 화면 · 본문');
  expect(settings).toContain('회원 전용 글은 요약');
  expect(settings).not.toContain('naver_search');
});
it('shows terminated shopping and dynamic integration counts', () => {
  const drawer = readFileSync('src/components/internal/IntegrationsDrawer.tsx', 'utf8');
  expect(drawer).toContain('서비스 종료');
  const layout = readFileSync('src/app/pipeline/layout.tsx', 'utf8');
  expect(layout).not.toContain('/6');
  expect(layout).toContain('entries?.length');
});

it('doubles Naver resume spacing to two seconds', () => {
  const channels = ['naver_blog', 'naver_cafe'];
  expect(increasedResumeIntervals(channels, {}, {perChannel: Object.fromEntries(channels.map(s => [s, limits(s)]))})).toEqual({naver_blog: 2, naver_cafe: 2});
});
