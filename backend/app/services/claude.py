import requests

from app.config import settings

CLAUDE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_HEADERS = {
    "x-api-key": settings.claude_api_key,
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json",
}


def call_claude(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "claude-sonnet-4-20250514",
    timeout: int = 60,
) -> str | None:
    """Call Claude API and return the text response."""
    try:
        resp = requests.post(
            CLAUDE_URL,
            headers=CLAUDE_HEADERS,
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()["content"][0]["text"]
        return None
    except Exception:
        return None
