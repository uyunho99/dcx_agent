import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
import { LayerTabs } from './LayerTabs';
import { QualityBadges } from './QualityBadges';
import { ChannelBar } from './ChannelBar';
import { KSuggestChart } from './KSuggestChart';
import { ProvisionalBadge } from '../ds';

it('shows the current step and visible, titled reasons for locked layers', () => {
  const html = renderToStaticMarkup(createElement(LayerTabs, {
    value: '6-A', onChange: () => {}, confirm: { clusters: '3/5', personas: '0/12', contexts: '0/31' },
  }));
  expect(html).toMatch(/<button[^>]*aria-current="step"[^>]*>.*?6-A/);
  expect(html.match(/aria-disabled="true"/g)).toHaveLength(2);
  for (const reason of ['6-A 확정 후', '6-B 확정 후']) {
    expect(html).toContain(`title="${reason}"`);
    expect(html).toContain(`잠김 · ${reason}`);
  }
});

it('blocks locked navigation and opens completed predecessors', () => {
  const onChange = vi.fn();
  const props = { value: '6-A' as const, onChange, confirm: { clusters: '3/5', personas: '0/12', contexts: '0/31' } };
  LayerTabs(props).props.children[1].props.onClick();
  expect(onChange).not.toHaveBeenCalled();
  LayerTabs({ ...props, confirm: { ...props.confirm, clusters: '5/5' } }).props.children[1].props.onClick();
  expect(onChange).toHaveBeenCalledWith('6-B');
});

it('does not unlock empty or malformed confirmation totals', () => {
  for (const count of ['0/0', '', 'bad']) {
    const html = renderToStaticMarkup(createElement(LayerTabs, { value: '6-A', onChange: () => {}, confirm: { clusters: count, personas: '1/1', contexts: '0/1' } }));
    expect(html.match(/aria-disabled="true"/g)).toHaveLength(2);
  }
});

it('includes readable warning text with quality values', () => {
  const html = renderToStaticMarkup(createElement(QualityBadges, { quality: { cohesion: 0.54, boundary: 0.16, ari: 0.69 } }));
  for (const label of ['응집 0.54 · 분리 검토', '경계 16% · 경계 검토', '안정 0.69 · 불안정']) expect(html).toContain(label);
  expect(html.match(/ds-warning/g)).toHaveLength(3);
});

it('uses strict quality thresholds and the L2 stability threshold', () => {
  const html = renderToStaticMarkup(createElement(QualityBadges, { layer: 'L2', quality: { cohesion: 0.6, boundary: 0.15, ari: 0.6 } }));
  expect(html).not.toContain('ds-warning');
  expect(renderToStaticMarkup(createElement(QualityBadges, { layer: 'L2', quality: { ari: 0.59 } }))).toContain('불안정');
  expect(renderToStaticMarkup(createElement(QualityBadges, { quality: { ari: null } }))).not.toContain('안정');
});

it('warns at 80 percent channel share, with readable source percentages', () => {
  const html = renderToStaticMarkup(createElement(ChannelBar, { channels: { 카페: 0.8, 유튜브: 0.2 } }));
  expect(html).toContain('한 채널 편중');
  expect(html).toContain('카페 80%');
  expect(html).toContain('유튜브 20%');
  expect(html).toContain('width:80%');
  expect(renderToStaticMarkup(createElement(ChannelBar, { channels: { 카페: 0.799, 유튜브: 0.201 } }))).not.toContain('한 채널 편중');
});

it('handles empty channel data', () => {
  const html = renderToStaticMarkup(createElement(ChannelBar, { channels: {} }));
  expect(html).toContain('채널 정보가 없습니다.');
  expect(html).not.toContain('한 채널 편중');
});

it('renders Korean channel names for the 6-A distribution', () => {
  const html = renderToStaticMarkup(createElement(ChannelBar, {
    channels: { naver_cafe: 0.2, naver_blog: 0.2, youtube: 0.2, ppomppu: 0.2, clien: 0.2 },
  }));
  expect(html).toContain('네이버 카페 20% · 네이버 블로그 20% · 유튜브 20% · 뽐뿌 20% · 클리앙 20%');
});

it('falls back to the raw code for an unknown channel', () => {
  const html = renderToStaticMarkup(createElement(ChannelBar, { channels: { new_channel: 1 } }));
  expect(html).toContain('new_channel 100%');
});

it.each(['false', 'true', undefined])('respects the crawl fixture visibility rule with internal tools set to %s', async (flag) => {
  vi.stubEnv('NEXT_PUBLIC_INTERNAL_TOOLS', flag);
  vi.resetModules();
  try {
    const { ChannelBar: ConfiguredChannelBar } = await import('./ChannelBar');
    const html = renderToStaticMarkup(createElement(ConfiguredChannelBar, { channels: { fixture: 0.8, youtube: 0.2 } }));
    const fixtureOnly = renderToStaticMarkup(createElement(ConfiguredChannelBar, { channels: { fixture: 1 } }));
    expect(html).toContain('유튜브 20%');
    if (flag === 'false') {
      expect(html).not.toContain('fixture');
      expect(html).not.toContain('개발용 샘플');
      expect(html).not.toContain('width:80%');
      expect(html).not.toContain('한 채널 편중');
      expect(fixtureOnly).toContain('채널 정보가 없습니다.');
    } else {
      expect(html).toContain('개발용 샘플 80%');
      expect(html).toContain('width:80%');
      expect(html).toContain('한 채널 편중');
      expect(fixtureOnly).toContain('개발용 샘플 100%');
    }
  } finally {
    vi.unstubAllEnvs();
    vi.resetModules();
  }
});

it('exports a provisional badge with fixed Korean copy', () => {
  expect(renderToStaticMarkup(createElement(ProvisionalBadge))).toContain('잠정</span>');
});

it('describes every k and silhouette value and highlights the suggestion', () => {
  const html = renderToStaticMarkup(createElement(KSuggestChart, { k: 5, silhouette: { 3: 0.06, 4: 0.07, 5: 0.09, 6: 0.08, 7: 0.07, 8: 0.06 }, sample: 20000 }));
  expect(html).toContain('role="img"');
  expect(html).toContain('aria-label="k별 실루엣: k 3: 0.06, k 4: 0.07, k 5: 0.09, k 6: 0.08, k 7: 0.07, k 8: 0.06. 제안 k = 5"');
  expect(html).toContain('표본 20,000건');
  expect(html).toContain('<circle');
});

it('renders empty, single, flat and negative silhouette data without invalid coordinates', () => {
  const cases: Record<number, number>[] = [{}, { 3: 0 }, { 3: -0.2, 4: -0.2 }, { 3: -0.5, 4: 0.5 }];
  for (const silhouette of cases) {
    const html = renderToStaticMarkup(createElement(KSuggestChart, { k: 3, silhouette, sample: 12 }));
    expect(html).not.toMatch(/NaN|Infinity/);
    if (!Object.keys(silhouette).length) expect(html).toContain('실루엣 정보가 없습니다.');
  }
});
