"""Editable keyword stopwords (D-246/D-249); never filter LDA training tokens."""
from collections.abc import Iterable
import hashlib


STOPWORDS: frozenset[str] = frozenset('''
사용 생각 정도 경우 제품 사람 문제 부분 이번 때문 진짜 정말 하나 자체
이상 이하 정보 내용 방법 상황 느낌 필요 가능 시간 처음 지금 요즘 마음 후기 리뷰
관련 대한 통해 위해 기준 사실 오늘 내일 어제 최근 현재 당시 이후 이전
동안 순간 계속 항상 자주 가끔 먼저 나중 다시 모두 전부 전체 대부분 일부
여러 서로 각각 직접 따로 그냥 조금 아주 너무 매우 가장 더욱 거의 무척
다른 같은 이런 그런 저런 어떤 무슨 아무 여러가지 이것 그것 저것 여기 거기 저기
이유 결과 과정 방식 차이 점점 보통 일반 기본 실제 개인 자신 우리 여러분
누구 무엇 어디 언제 확인 참고 설명 이야기 얘기
'''.split())


def is_stopword(word: str, bk: str | None) -> bool:
    """Match generic noise and product names, ignoring product-name whitespace."""
    compact = ''.join(word.split())
    product = ''.join((bk or '').split())
    return (len(compact) <= 1 or compact.isdigit() or compact in STOPWORDS
            or bool(product and product in compact))


def filter_words(words: Iterable[str], bk: str | None) -> list[str]:
    """Keep the original order and spelling of surviving keywords."""
    return [word for word in words if not is_stopword(word, bk)]


def stopwords_signature() -> dict:
    """Fingerprint the single editable list using sorted, newline-separated UTF-8."""
    digest = hashlib.sha256('\n'.join(sorted(STOPWORDS)).encode()).hexdigest()[:12]
    return {'count': len(STOPWORDS), 'hash': digest}
