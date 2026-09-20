"""Explicit bounded free-source probe. Not called by default config checks."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from . import adapters


def main():
    parser = argparse.ArgumentParser(description='显式调用免费源；每源一次，默认不重试，不写研究数据库。')
    parser.add_argument('--sources', default='rss,world_bank,gdelt')
    args = parser.parse_args()
    choices = args.sources.split(',')
    if any(item not in ('rss', 'world_bank', 'gdelt') for item in choices):
        parser.error('支持 rss,world_bank,gdelt')
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    report = {'checked_at': now, 'mode': 'real_network', 'tls_verification': True,
              'credentials': False, 'paid_calls': 0, 'requests': []}
    for adapter in choices:
        source = {'id': 'probe-' + adapter, 'adapter': adapter,
                  'config': {'query': 'climate', 'feed_url': 'https://www.federalreserve.gov/feeds/press_all.xml',
                             'countries': ['CHN'], 'indicators': list(adapters.INDICATORS)},
                  'rights': {'fetch': True, 'store': True, 'display': True, 'export': True, 'ai': False}}
        job = {'checkpoint': {}}
        url, headers = adapters.request_for(source, job)
        start = time.monotonic()
        record = {'adapter': adapter, 'url': url}
        try:
            response = adapters.fetch(url, headers)
            record.update({'http_status': response.status, 'bytes': len(response.body),
                           'sha256': hashlib.sha256(response.body).hexdigest(),
                           'headers': response.headers})
            parsed = adapters.parse(source, job, response, now)
            record.update({'evidence_count': len(parsed['evidence']),
                           'observation_count': len(parsed['observations']), 'data_as_of': parsed['data_as_of'],
                           'evidence': [{k: item.get(k) for k in ('title', 'url', 'published_at', 'source_updated_at', 'provider_seen_at', 'material_type', 'source_record_id')} for item in parsed['evidence'][:20]],
                           'observations': parsed['observations']})
        except adapters.FetchError as exc:
            record.update({'error_code': exc.code, 'reason': exc.message, 'retry_after': exc.retry_after})
        record['elapsed_seconds'] = round(time.monotonic() - start, 3)
        report['requests'].append(record)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item.get('error_code') is None for item in report['requests']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
