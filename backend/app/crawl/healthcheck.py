"""One-page, three-detail adapter smoke check."""
import argparse

from app.crawl.adapters import REGISTRY, available_sources
from app.crawl.adapters.base import AdapterBlocked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=sorted(REGISTRY))
    parser.add_argument('--keyword', default='에어컨')
    args = parser.parse_args(argv)
    failed = False
    for source in [args.source] if args.source else available_sources():
        blocked = False
        detail_ok = '0/3'
        try:
            adapter = REGISTRY[source]()
            page = adapter.list_page(args.keyword, None)
            list_ok = f'{len(page.items)}/{len(page.items)}'
        except Exception as exc:
            list_ok = 'FAIL'
            blocked = isinstance(exc, AdapterBlocked)
            failed = True
        else:
            success, errors = 0, False
            for item in page.items[:3]:
                try:
                    adapter.fetch(item)
                    success += 1
                except Exception as exc:
                    errors = failed = True
                    blocked |= isinstance(exc, AdapterBlocked)
            detail_ok = 'FAIL' if errors else f'{success}/3'
        print(f'{source}: list_ok {list_ok} · detail_ok {detail_ok} · blocked {str(blocked).lower()}')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
