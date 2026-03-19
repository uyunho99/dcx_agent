import re
import json
import requests

from app.config import settings


def clean_text(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"&lt;", "<", t)
    t = re.sub(r"&gt;", ">", t)
    return t.strip()


def get_llm_predictions(batch: list, bk: str, problem_def: str) -> list[int]:
    try:
        prompt = f'제품: "{bk}"\n문제정의: {problem_def}\n\n아래 글들이 해당 제품 관련인지 판단. 1(관련) 또는 0(무관)으로만.\n\n'
        for j, item in enumerate(batch):
            prompt += f"{j+1}. {item.get('title','')} - {item.get('desc','')[:100]}\n"
        prompt += "\n답변: 1,0,1,0,..."
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.claude_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        if resp.status_code == 200:
            nums = re.findall(r"[01]", resp.json()["content"][0]["text"])
            preds = [int(n) for n in nums[: len(batch)]]
            while len(preds) < len(batch):
                preds.append(0)
            return preds
    except Exception:
        pass
    return [0] * len(batch)
