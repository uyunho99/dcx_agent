type Pair = '을/를' | '이/가' | '은/는' | '와/과';

/** Return the particle for the final Hangul syllable or Korean digit/letter name. */
export function josa(word: string, pair: Pair): string {
  const last = Array.from(word.trim().replace(/[”’"'」』)\]]+$/u, '')).at(-1) ?? '';
  const code = last.charCodeAt(0);
  const batchim = code >= 0xac00 && code <= 0xd7a3
    ? (code - 0xac00) % 28 !== 0
    : /^[013678]$/.test(last) || /^[LMNR]$/i.test(last);
  const [first, second] = pair.split('/');
  return pair === '와/과' ? (batchim ? second : first) : (batchim ? first : second);
}
