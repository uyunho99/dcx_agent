import { describe, expect, it } from 'vitest';
import { keywordLabel, keywordTitle } from './keywordDisplay';

const kw = '귀촌휴식죄책감';

describe('keywordLabel', () => {
  it('uses the trimmed display value when present', () => {
    expect(keywordLabel({ kw, display: '  귀촌 휴식 죄책감  ' })).toBe('귀촌 휴식 죄책감');
  });

  it('falls back to the original keyword when display is absent', () => {
    expect(keywordLabel({ kw })).toBe(kw);
  });

  it('falls back to the original keyword when display is empty or whitespace-only', () => {
    for (const display of ['', ' \t\n ']) expect(keywordLabel({ kw, display })).toBe(kw);
  });
});

describe('keywordTitle', () => {
  it('exposes the original keyword when the label differs', () => {
    expect(keywordTitle({ kw, display: ' 귀촌 휴식 죄책감 ' })).toBe(kw);
  });

  it('omits the title when the label equals the original keyword', () => {
    for (const display of [undefined, '', ' \t\n ', kw, ` ${kw} `]) {
      expect(keywordTitle({ kw, display })).toBeUndefined();
    }
  });
});
