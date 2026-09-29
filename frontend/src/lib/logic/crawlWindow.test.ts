import { expect, it } from 'vitest';
import { crawlWindow } from './crawlWindow';
it('renders all rows through the 300 row threshold', () => {
  expect(crawlWindow(Array(300).fill(48), 500, 100)).toEqual({start:0,end:300,before:0,after:0});
});
it('windows variable heights including expanded rows and overscan', () => {
  const heights = Array(301).fill(48); heights[0] = 200;
  expect(crawlWindow(heights, 200, 96, 0)).toEqual({start:1,end:3,before:200,after:298*48});
});
it('clamps stale scroll after collapse and handles empty data', () => {
  expect(crawlWindow([], 100, 600).end).toBe(0);
  const result = crawlWindow(Array(301).fill(48), 999999, 96, 2);
  expect(result.end).toBe(301); expect(result.start).toBeLessThan(301);
  expect(result.before + (result.end-result.start)*48 + result.after).toBe(301*48);
});
