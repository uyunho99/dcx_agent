import re
import json
from datetime import datetime

from app.services.s3 import load_data, save_json, load_json, list_objects
from app.services.pinecone_svc import search_similar
from app.services.claude import call_claude
from app.jobs.manager import job_manager


def run_persona(config: dict) -> None:
    sid = config.get("sid", "s0")
    bk = config.get("bk", "")
    job_manager.set("persona", sid, {"status": "running", "progress": 0})

    try:
        all_data = load_data(f"clusters_refined/{sid}/data_")
        if not all_data:
            all_data = load_data(f"clusters/{sid}/cluster_")
        if not all_data:
            job_manager.set("persona", sid, {"status": "error", "error": "no data"})
            return

        clusters = {}
        for item in all_data:
            cid = item.get("cluster", 0)
            if cid not in clusters:
                clusters[cid] = []
            clusters[cid].append(item)

        job_manager.update("persona", sid, progress=20)

        # Load past good naming examples
        past_examples = ""
        try:
            examples_data = load_json("naming_examples/good_names.json")
            if examples_data:
                examples = examples_data if isinstance(examples_data, list) else []
                if examples:
                    past_examples = "\n## 과거 좋은 네이밍 사례 (참고용, 그대로 복사 금지!)\n"
                    for ex in examples[-10:]:
                        past_examples += (
                            f"- 산업:{ex.get('industry', '')}, "
                            f"클러스터:{ex.get('cluster', '')}, "
                            f"페르소나:{', '.join(ex.get('personas', []))}\n"
                        )
        except Exception:
            pass

        all_cluster_text = ""
        for cid in sorted(clusters.keys()):
            items = clusters[cid][:20]
            try:
                rag_docs = search_similar(
                    sid, " ".join([x.get("kw", "") for x in clusters[cid][:5]]), top_k=10,
                )
                if rag_docs:
                    items = [{"title": d.get("title", ""), "desc": d.get("desc", "")} for d in rag_docs]
            except Exception:
                pass
            text = "\n".join([f"- {x.get('title', '')} | {x.get('desc', '')[:100]}" for x in items])
            kw_set = set([x.get("kw", "") for x in clusters[cid] if x.get("kw", "")])
            all_cluster_text += (
                f"\n### 클러스터 {cid + 1} ({len(clusters[cid])}건, 키워드다양성: {len(kw_set)}개)\n{text}\n"
            )

        prompt = f"""제품군: "{bk}"

아래는 소비자 데이터를 클러스터링한 결과입니다:
{all_cluster_text}

## 임무
{past_examples}
각 클러스터에 이름을 붙이고, 각 클러스터의 데이터 크기와 다양성에 따라 페르소나를 도출해주세요.

## 페르소나 수 결정 기준 (SNA 기반)
- 데이터 50건 미만: 페르소나 1개
- 데이터 50~200건: 페르소나 2개
- 데이터 200건 이상: 페르소나 3개
- 클러스터 내 키워드 다양성이 높으면 +1개 추가 가능
- 전체 페르소나 수는 클러스터 수의 1.5~2배가 적정

## 네이밍 규칙
- 제품명 직접 언급 금지
- 상황/행동/심리를 위트있고 은유적으로 표현

## 출력 형식 (JSON)
[
  {{
    "cluster_id": 1,
    "cluster_name": "클러스터명",
    "personas": [
      {{
        "name": "페르소나명",
        "situation": "상황",
        "pain_point": "핵심 고민",
        "insight": "마케팅 인사이트"
      }}
    ]
  }}
]

JSON만 출력:"""

        text = call_claude(prompt, max_tokens=8000, timeout=180)
        job_manager.update("persona", sid, progress=80)

        personas = []
        if text:
            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                personas = json.loads(match.group())

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = {
            "bk": bk, "personas": personas,
            "num_clusters": len(clusters), "total_docs": len(all_data), "timestamp": ts,
        }
        save_json(f"personas/{sid}/result_{ts}.json", result)

        job_manager.set("persona", sid, {
            "status": "done", "progress": 100, "personas": personas,
            "num_clusters": len(clusters), "total_docs": len(all_data),
        })
    except Exception as e:
        job_manager.set("persona", sid, {"status": "error", "error": str(e)})
