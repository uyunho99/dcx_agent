import type { EvidenceStatus, EvidenceItemView, EvidenceContextResponse } from '@/lib/types';

// Wire fields copied from routers/evidence.py and assemble.stage_report, plus D-266.
export const stage7Fixture = {
  coverage_supplements:0, query_gen_fail:0, new_expansions:0, rare_fallback:0,
  dpp_fill:0, untagged:0, lazy_dims:0, llm_calls:91, tag_calls:84, cache_hits:0,
  relevant_false:7, coverage:{}, band_exposure_ratios:{}, novelty_distribution:{},
  escalation_candidates:{}, reason_code:{}, known_match_distribution:{},
  per_tab_counts:{all:10,new:8}, params:{},
};
export const evidenceStatusFixture: EvidenceStatus = {
  status:'running', run:'generation', progress:1/3, tagCalls:84,
  contexts:[{id:'C1',personaId:'P',name:'상황',status:'done',coverage:5,
    counts:{all:10,new:8},error:null,knownChanged:false}],
};
export const evidenceItemFixture: EvidenceItemView = {
  docId:'d',source:'youtube',location:{field:'comment',idx:2},
  quoteSource:{field:'comment',idx:2,text:'😀 인용 끝'},
  quote:{text:'인용',start:2,end:4,verified:true},text:'별개의 본문 미리보기',
  tags:['feel'],band:'edge',novelty:'high',noveltyShown:true,
  known:{handed:false,kiId:'ki_second'},noveltyReason:'새로운 이유',knownMatch:'ki_second',rare:true,role:'support',
};
export const evidenceContextFixture: EvidenceContextResponse = {
  context:{context_id:'C1',persona_id:'P',name:'상황',name_draft:'상황',
    action:'행동',action_draft:'행동',keywords:[],dominant_constraint:null,
    dims_summary:{},quality:{},flags:[],confirmed_at:'2026-10-02T00:00:00Z'},tab:'new',items:[evidenceItemFixture],
  counter:[],rare:[],queries:[],queryFailed:false,excludedKnown:7,undifferentiated:[],
};

export const knownInsightsFixture = ['ki_first','ki_second'].map(id => ({
  id,type:'statement' as const,text:'알고 있는 내용',doc_id:null,from:'drawer' as const,
  createdAt:'2026-10-02T00:00:00Z',vectorRow:null,warning:null,
}));
