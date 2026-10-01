import re
import unicodedata

from bs4 import BeautifulSoup


def clean_html(text) -> str:
    # Avoid changing whitespace of already extracted crawl text.
    soup = BeautifulSoup(text or '', 'html.parser')
    for tag in soup(['script', 'style']):
        tag.decompose()
    for tag in soup.find_all(['br', 'p', 'div', 'li']):
        tag.insert_after('\n')
    return soup.get_text().strip()


def strip_boilerplate(text, phrases) -> tuple[str, int]:
    count = 0
    for phrase in sorted(set(phrases), key=lambda p: (-len(p), p)):
        if phrase:
            count += text.count(phrase)
            text = text.replace(phrase, '')
    return text.strip(), count


def token_text(text) -> str:
    return re.sub(r'\s+', ' ', ''.join(
        ' ' if unicodedata.category(c)[0] in 'PSC' else c for c in text)).strip()
