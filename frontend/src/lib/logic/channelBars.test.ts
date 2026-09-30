import { describe, expect, it } from 'vitest';
import { channelBars } from './channelBars';
describe('channelBars', () => {
  it('uses surviving counts and within-keyword ratios including dashed zero', () => {
    expect(channelBars({a:{listed:12,filtered:2},b:{listed:30,filtered:0},c:{listed:0,filtered:0}})).toEqual([
      {source:'a',count:10,ratio:.25,dashed:false}, {source:'b',count:30,ratio:.75,dashed:false}, {source:'c',count:0,ratio:0,dashed:true},
    ]);
  });
  it('handles empty, all zero, negative and nonfinite values', () => {
    expect(channelBars({})).toEqual([]);
    expect(channelBars({a:{listed:0,filtered:2},b:{listed:NaN,filtered:0}}).every(b => b.dashed && b.ratio === 0)).toBe(true);
  });
});
