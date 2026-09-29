"""Generate a deterministic synthetic air-conditioner review corpus."""
import argparse
import csv
from pathlib import Path


def write_corpus(path: Path, rows: int = 200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['review'])
        writer.writeheader()
        for i in range(rows):
            keyword = f'냉방{i % 4 + 1}단어{i % 42}'
            writer.writerow({'review': f'{keyword} 에어컨 사용 후기 {i}: 실내 온도와 소음, 전기요금을 비교하며 사용했습니다. 설치 공간과 청소 경험도 기록합니다.'})


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
