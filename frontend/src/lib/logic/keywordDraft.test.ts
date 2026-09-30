import { expect, it } from 'vitest';
import { restoreKeywordDraft } from './keywordDraft';
it('restores direction verbatim only for matching generation, including old drafts',()=>{
 expect(restoreKeywordDraft({round:1,gen:2,decisions:[],direction:'  영유아 맥락  '},2)?.direction).toBe('  영유아 맥락  ');
 expect(restoreKeywordDraft({round:1,gen:1,decisions:[],direction:'old'},2)).toBeUndefined();
 expect(restoreKeywordDraft({round:1,gen:2,decisions:[]},2)?.direction).toBe('');
});
