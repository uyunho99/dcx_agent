"""Generate a deterministic synthetic air-conditioner review corpus."""
import argparse
import csv
import json
from pathlib import Path


def write_corpus(path: Path, rows: int = 200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).parent / 'llm'
    words = [item['kw'] for n in range(1, 5)
             for item in json.loads((fixtures / f'kw_round_{n}.json').read_text(encoding='utf-8'))['keywords']]
    # Distribute five literal fixture terms per review: with 200 rows every
    # term occurs at least three times, without putting all terms in each row.
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['review'])
        writer.writeheader()
        for i in range(rows):
            keyword = ', '.join(words[(i * 5 + offset) % len(words)] for offset in range(5))
            # Preserve the original synthetic marker used by existing offline
            # integration clients while adding the shipped QA vocabulary.
            legacy_keyword = f'냉방{i % 4 + 1}단어{i % 42}'
            writer.writerow({'review': f'{legacy_keyword} {keyword} 에어컨 사용 후기 {i}: 실내 온도와 전기요금을 비교하며 사용했습니다. 설치 공간과 청소 경험도 기록합니다.'})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--rows', type=int, default=200)
    args = parser.parse_args()
    if args.rows < 0:
        parser.error('--rows must be nonnegative')
    write_corpus(args.path, args.rows)


if __name__ == '__main__':
    main()
