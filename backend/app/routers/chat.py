import re
import json
from datetime import datetime
from fastapi import APIRouter

from app.services.pinecone_svc import search_similar
from app.services.s3 import load_data, list_objects, load_json, save_json
from app.services.claude import call_claude
from app.jobs.manager import job_manager
from app.models.schemas import ChatRequest, InsightChatRequest

router = APIRouter()


@router.post("/chat")
def chat_agent(req: ChatRequest):
    try:
        sid, query, pipeline_ctx = req.sid, req.query, req.pipeline_context

        similar_docs = search_similar(sid, query, top_k=5)

        persona_info = ""
        try:
            objects = list_objects(f"personas/{sid}/")
            if objects:
                latest = sorted(objects, key=lambda x: x["Key"], reverse=True)[0]
                persona_data = load_json(latest["Key"])
                if persona_data:
                    persona_info = json.dumps(persona_data.get("personas", []), ensure_ascii=False, indent=2)
        except Exception:
            pass

        cluster_info = ""
        try:
            cd = load_data(f"clusters_refined/{sid}/data_")
            if not cd:
                cd = load_data(f"clusters/{sid}/cluster_")
            if cd:
                cl: dict[int, list] = {}
                for it in cd:
                    c = it.get("cluster", 0)
                    if c not in cl:
                        cl[c] = []
                    cl[c].append(it)
                cluster_info = f"총 {len(cl)}개 클러스터, {len(cd)}건\n"
                for c in sorted(cl.keys()):
                    s = ", ".join([x.get("title", "")[:30] for x in cl[c][:3]])
                    cluster_info += f"  클러스터{c + 1} ({len(cl[c])}건): {s}\n"
        except Exception:
            pass

        rag_context = ""
        for doc in similar_docs:
            rag_context += f"- {doc.get('title', '')} | {doc.get('desc', '')[:200]}\n"

        prompt = f"""당신은 DCX 파이프라인 소비자 인사이트 전문가입니다.

## 파이프라인 상태
{pipeline_ctx if pipeline_ctx else "정보 없음"}

## 페르소나 분석 결과
{persona_info if persona_info else "아직 분석 전"}

## 클러스터 정보
{cluster_info if cluster_info else "없음"}

## RAG 검색 결과
{rag_context if rag_context else "없음"}

## 역할
- 파이프라인 각 단계 결과를 분석/평가
- 클러스터/페르소나에 대한 개선 제안
- 마케팅 인사이트와 실행 가능한 전략 제안
- 사용자 피드백을 반영한 조언
- 키워드 추가 요청 처리

## 키워드 추가 기능
사용자가 키워드 추가를 요청하면 (예: "화재 추가해줘") 답변 마지막 줄에 반드시:
ADDED_KEYWORDS: 화재, 침수, 누수
형식으로 작성하세요. 1~2단어 명사형 키워드만. 시스템이 자동으로 추가합니다.

## 질문
{query}

절대로 이모티콘, 이모지, 특수문자(✅🔥💡📊 등)를 사용하지 마세요. 마크다운 기호(**,##,###,- 등)도 사용하지 마세요. 순수 텍스트 문장으로만 답변하세요. 한국어로 답변:"""

        answer = call_claude(prompt, max_tokens=2000)
        if answer:
            added_kw = []
            kw_match = re.search(r"ADDED_KEYWORDS:\s*(.+)", answer)
            if kw_match:
                kw_str = kw_match.group(1).strip()
                added_kw = [k.strip() for k in kw_str.split(",") if k.strip()]
                answer = re.sub(r"ADDED_KEYWORDS:\s*.+", "", answer).strip()
                if added_kw:
                    answer += "\n\n" + ", ".join(added_kw) + " 키워드가 추가되었습니다."
            return {"status": "ok", "answer": answer, "sources": similar_docs, "added_keywords": added_kw}
        return {"status": "error", "answer": "API 오류", "sources": []}
    except Exception as e:
        return {"status": "error", "answer": f"오류가 발생했습니다: {str(e)}", "sources": []}


@router.post("/insight-chat")
def insight_chat(req: InsightChatRequest):
    """인사이트 챗봇 - 분석 + 수정 명령 처리."""
    try:
        sid, query, bk = req.sid, req.query, req.bk

        persona_data = None
        persona_key = None
        try:
            objects = list_objects(f"personas/{sid}/")
            if objects:
                latest = sorted(objects, key=lambda x: x["Key"], reverse=True)[0]
                persona_key = latest["Key"]
                persona_data = load_json(persona_key)
        except Exception:
            pass

        persona_json = json.dumps(
            persona_data.get("personas", []) if persona_data else [], ensure_ascii=False, indent=2,
        )

        similar_docs = search_similar(sid, query, top_k=5)

        cluster_samples = ""
        try:
            cd = load_data(f"clusters_refined/{sid}/data_")
            if not cd:
                cd = load_data(f"clusters/{sid}/cluster_")
            if cd:
                cl_map: dict[int, list] = {}
                for it in cd:
                    c = it.get("cluster", 0)
                    if c not in cl_map:
                        cl_map[c] = []
                    cl_map[c].append(it)
                for c in sorted(cl_map.keys()):
                    items = cl_map[c]
                    kw_cnt: dict[str, int] = {}
                    for it in items:
                        kw = it.get("kw", "")
                        if kw:
                            kw_cnt[kw] = kw_cnt.get(kw, 0) + 1
                    top_kw = sorted(kw_cnt.items(), key=lambda x: -x[1])[:5]
                    cluster_samples += f"\n클러스터 {c + 1} ({len(items)}건, 주요키워드: {', '.join([k[0] for k in top_kw])}):\n"
                    for it in items[:2]:
                        cluster_samples += f"  - [{it.get('kw', '')}] {it.get('title', '')} | {it.get('desc', '')[:100]}\n"
        except Exception:
            pass

        rag_context = (
            "\n".join([f"- {d.get('title', '')} | {d.get('desc', '')[:150]}" for d in similar_docs])
            if similar_docs else "없음"
        )

        prompt = f"""당신은 DCX 소비자 인사이트 전문가이자 데이터 편집 에이전트입니다.

## 현재 페르소나 데이터
{persona_json}

## 클러스터별 원문 샘플
{cluster_samples if cluster_samples else "없음"}

## RAG 검색 결과
{rag_context}

## 사용자 메시지
{query}

## 역할
사용자의 메시지를 분석해서 두 가지 중 하나를 수행하세요:

### A) 분석/질문인 경우
마케팅 인사이트, 전략 제안, 페르소나 분석 등을 답변하세요.
이 경우 JSON 블록 없이 텍스트만 응답하세요.

### B) 수정 명령인 경우 (예: "클러스터 합쳐줘", "페르소나 이름 바꿔줘", "인사이트 수정해줘")
1. 수정 사항을 설명하고
2. 반드시 아래 형식의 JSON 블록을 포함하세요:

```MODIFIED_DATA
[수정된 전체 페르소나 배열 JSON]
```

수정 시 규칙:
- 기존 데이터 구조(cluster_id, cluster_name, personas 배열) 유지
- 클러스터 합치기: 두 클러스터의 personas를 하나로 합치고 새 이름 부여
- 페르소나 수정: name, situation, pain_point, insight 필드 수정 가능
- 클러스터 삭제: 해당 클러스터를 배열에서 제거
- 응답은 한국어로
- 절대로 이모티콘, 이모지, 특수문자를 사용하지 마세요
- 마크다운 기호(**,##,###,- 불릿)도 사용하지 마세요
- 순수 텍스트 문장으로만 답변

절대로 이모티콘, 이모지, 특수문자(✅🔥💡📊 등)를 사용하지 마세요. 마크다운 기호(**,##,###,- 등)도 사용하지 마세요. 순수 텍스트 문장으로만 답변하세요. 한국어로 답변:"""

        answer = call_claude(prompt, max_tokens=4000, timeout=120)
        if answer:
            modified = False
            mod_match = re.search(r"```MODIFIED_DATA\s*\n([\s\S]*?)\n```", answer)
            if mod_match:
                try:
                    new_personas = json.loads(mod_match.group(1))
                    if isinstance(new_personas, list) and len(new_personas) > 0:
                        if persona_data:
                            persona_data["personas"] = new_personas
                        else:
                            persona_data = {"bk": bk, "personas": new_personas}

                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_json(f"personas/{sid}/result_{ts}.json", persona_data)
                        job_manager.set("persona", sid, {
                            "status": "done", "progress": 100, "personas": new_personas,
                        })
                        modified = True
                except Exception:
                    pass

            clean_answer = re.sub(r"```MODIFIED_DATA\s*\n[\s\S]*?\n```", "", answer).strip()
            return {"status": "ok", "answer": clean_answer, "modified": modified, "sources": similar_docs}

        return {"status": "error", "answer": "API 오류", "modified": False, "sources": []}
    except Exception as e:
        return {"status": "error", "answer": f"오류: {str(e)}", "modified": False, "sources": []}
