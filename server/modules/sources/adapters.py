"""Free provider adapters; network payloads remain untrusted data."""
from __future__ import annotations

import email.utils
import ipaddress
import json
import socket
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

UTC = timezone.utc
ALLOWED_HOSTS = {'api.gdeltproject.org', 'www.federalreserve.gov', 'api.worldbank.org'}
INDICATORS = {'NY.GDP.MKTP.CD': ('GDP（现价美元）', 'USD'), 'SP.POP.TOTL': ('人口总数', 'persons')}


class FetchError(Exception):
    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code, self.message, self.retry_after = code, message, retry_after


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict = field(default_factory=dict)


def public_host(host):
    if host not in ALLOWED_HOSTS:
        raise FetchError('domain_not_allowed', '该域名未通过采集许可审核，只能登记原文链接。')
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise FetchError('unsafe_address', '来源解析到了非公网地址，已阻止采集。')
    return sorted(addresses, key=lambda item: ':' in item)[0]


def fetch(url, headers=None):
    """Use system curl's trusted CA. No redirects, credentials or arbitrary hosts."""
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise FetchError('unsafe_url', '采集仅支持已审核域名的 HTTPS 地址。')
    try:
        address = public_host(parsed.hostname)
    except OSError as exc:
        raise FetchError('dns_failed', '来源域名解析失败，请检查本机网络。') from exc
    if ':' in address:
        address = '[' + address + ']'
    with tempfile.TemporaryDirectory(prefix='world-insight-fetch-') as directory:
        header_file = Path(directory) / 'headers'
        args = ['/usr/bin/curl', '--disable', '--silent', '--show-error', '--proto', '=https',
                '--connect-timeout', '8', '--max-time', '20', '--max-filesize', '2097152',
                '--max-redirs', '0', '--resolve', f'{parsed.hostname}:443:{address}',
                '--user-agent', 'WorldInsight/0.1 (personal research; metadata only)',
                '--dump-header', str(header_file), '--write-out', '\nWI_HTTP_STATUS:%{http_code}']
        for key, value in (headers or {}).items():
            if key.lower() in ('if-none-match', 'if-modified-since') and '\n' not in value and '\r' not in value:
                args.extend(['--header', f'{key}: {value}'])
        args.append(url)
        try:
            result = subprocess.run(args, capture_output=True, timeout=25, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FetchError('network_failed', '来源请求失败或超时；历史资料仍可使用。') from exc
        if result.returncode:
            # Do not expose raw curl errors, URL query strings or inherited credentials.
            code = 'timeout' if result.returncode == 28 else 'network_failed'
            raise FetchError(code, f'来源请求未完成（curl {result.returncode}），请检查网络和系统证书。')
        body, _, status = result.stdout.rpartition(b'\nWI_HTTP_STATUS:')
        if len(body) > 2097152:
            raise FetchError('too_large', '来源响应超过 2 MiB，已拒绝解析。')
        response_headers = {}
        for line in header_file.read_text(errors='replace').splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                if key.lower() in ('etag', 'last-modified', 'retry-after', 'content-type'):
                    response_headers[key.lower()] = value.strip()
        return Response(int(status), body, response_headers)


def _check(response):
    if response.status == 304:
        return
    if response.status == 429:
        retry = response.headers.get('retry-after', '60')
        try:
            retry = max(5, min(86400, int(retry)))
        except (ValueError, TypeError):
            retry = 60
        raise FetchError('upstream_rate_limit', '上游返回限流，已退避；不会切换收费服务。', retry)
    if response.status != 200:
        raise FetchError('upstream_http', f'来源返回 HTTP {response.status}，未将其当作无匹配结果。')


def _json(response):
    _check(response)
    try:
        return json.loads(response.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FetchError('invalid_payload', '来源返回的内容不是有效 JSON，未将其当作空结果。') from exc


def _iso(value):
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value).astimezone(UTC).isoformat().replace('+00:00', 'Z')
    except (TypeError, ValueError, OverflowError):
        return None


def request_for(source, job):
    adapter, config = source['adapter'], source.get('config', {})
    checkpoint = job.get('checkpoint', {})
    if adapter == 'gdelt':
        params = {'query': job.get('query') or config.get('query', ''), 'mode': 'artlist',
                  'format': 'json', 'maxrecords': 250, 'sort': 'datedesc'}
        if checkpoint.get('window_start') and checkpoint.get('window_end'):
            for name, key in [('startdatetime', 'window_start'), ('enddatetime', 'window_end')]:
                params[name] = datetime.fromisoformat(checkpoint[key].replace('Z', '+00:00')).strftime('%Y%m%d%H%M%S')
        else:
            params['timespan'] = '1d'
        return 'https://api.gdeltproject.org/api/v2/doc/doc?' + urlencode(params), {}
    if adapter == 'rss':
        headers = {}
        for key, name in [('etag', 'If-None-Match'), ('last_modified', 'If-Modified-Since')]:
            if source.get(key):
                headers[name] = source[key]
        return config['feed_url'], headers
    if adapter == 'world_bank':
        countries = ';'.join(config.get('countries', ['CHN', 'USA']))
        indicators = ';'.join(config.get('indicators', list(INDICATORS)))
        params = {'source': 2, 'format': 'json', 'mrv': 5, 'per_page': 200,
                  'page': checkpoint.get('page', 1)}
        return f'https://api.worldbank.org/v2/country/{countries}/indicator/{indicators}?' + urlencode(params), {}
    raise FetchError('not_configured', '该来源没有启用的免费采集适配器。')


def parse(source, job, response, now):
    _check(response)
    result = {'evidence': [], 'observations': [], 'data_as_of': source.get('data_as_of'),
              'next_page': None, 'saturated': False, 'not_modified': response.status == 304,
              'etag': response.headers.get('etag'), 'last_modified': response.headers.get('last-modified')}
    if response.status == 304:
        return result
    base = {'source_id': source['id'], 'topic_id': job.get('topic_id'),
            'collected_at': now, 'discovered_at': now, 'status': 'unverified',
            'rights': dict(source['rights']), 'author': None, 'source_updated_at': None}
    if source['adapter'] == 'gdelt':
        payload = _json(response)
        if not isinstance(payload, dict) or not isinstance(payload.get('articles'), list):
            raise FetchError('invalid_payload', 'GDELT 响应缺少文章列表。')
        for item in payload['articles']:
            url = item.get('url', '')
            if not _external_link(url):
                continue
            seen = item.get('seendate')
            try:
                seen = datetime.strptime(seen, '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC).isoformat().replace('+00:00', 'Z')
            except (ValueError, TypeError):
                seen = None
            result['evidence'].append({**base, 'url': url, 'source_record_id': url,
                'title': str(item.get('title', '无标题'))[:2000], 'excerpt': '',
                'language': item.get('language') or 'unknown', 'publisher': item.get('domain'),
                'material_type': 'news', 'published_at': None, 'provider_seen_at': seen,
                'notes': 'GDELT 检索时间仅保留为提供者观察时间；原文发布时间尚未核对。'})
        result['saturated'] = len(payload['articles']) >= 250
        result['data_as_of'] = max((item.get('provider_seen_at') for item in result['evidence'] if item.get('provider_seen_at')), default=None)
    elif source['adapter'] == 'rss':
        if b'<!DOCTYPE' in response.body.upper() or b'<!ENTITY' in response.body.upper():
            raise FetchError('unsafe_xml', '拒绝含 DTD 或实体声明的 RSS。')
        try:
            root = ET.fromstring(response.body)
        except ET.ParseError as exc:
            raise FetchError('invalid_payload', 'RSS 格式无效。') from exc
        if root.tag != 'rss' or root.find('channel') is None:
            raise FetchError('invalid_payload', '来源不是支持的 RSS 2.0 文档。')
        for item in root.findall('./channel/item')[:500]:
            url = item.findtext('link') or ''
            searchable = ((item.findtext('title') or '') + ' ' + (item.findtext('description') or '')).casefold()
            keywords = [str(word).casefold() for word in job.get('keywords', []) if str(word).strip()]
            excluded = [str(word).casefold() for word in job.get('exclude_keywords', []) if str(word).strip()]
            if (keywords and not any(word in searchable for word in keywords)) or any(word in searchable for word in excluded):
                continue
            if not _external_link(url):
                continue
            result['evidence'].append({**base, 'url': url,
                'source_record_id': item.findtext('guid') or url,
                'title': (item.findtext('title') or '无标题')[:2000],
                'excerpt': (item.findtext('description') or '')[:4000], 'language': 'en',
                'publisher': 'Federal Reserve Board', 'material_type': 'official_statement',
                'published_at': _iso(item.findtext('pubDate'))})
        result['data_as_of'] = max((item['published_at'] for item in result['evidence'] if item['published_at']), default=None)
    elif source['adapter'] == 'world_bank':
        payload = _json(response)
        if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[0], dict) or not isinstance(payload[1], list):
            raise FetchError('invalid_payload', 'World Bank 响应缺少分页头或指标列表。')
        metadata, values = payload
        if int(metadata.get('pages', 1)) > int(metadata.get('page', 1)):
            result['next_page'] = int(metadata['page']) + 1
        result['data_as_of'] = metadata.get('lastupdated')
        for item in values:
            indicator = item.get('indicator', {}).get('id')
            if indicator not in INDICATORS:
                continue
            country = item.get('countryiso3code')
            period = item.get('date')
            if not country or not period:
                continue
            url = f'https://data.worldbank.org/indicator/{indicator}?locations={country}&date={period}'
            external_id = f'{indicator}:{country}:{period}'
            result['evidence'].append({**base, 'url': url, 'source_record_id': external_id,
                'title': f'{INDICATORS[indicator][0]} · {country} · {period}',
                'excerpt': json.dumps({'value': item.get('value'), 'period': period, 'unit': INDICATORS[indicator][1]}, ensure_ascii=False),
                'language': 'en', 'publisher': 'World Bank / WDI', 'material_type': 'dataset',
                'published_at': None, 'source_updated_at': metadata.get('lastupdated')})
            result['observations'].append({'source_id': source['id'], 'source_record_id': external_id,
                'topic_id': job.get('topic_id'), 'indicator': indicator, 'country_code': country,
                'value': item.get('value'), 'unit': INDICATORS[indicator][1], 'period': period,
                'frequency': 'annual', 'published_at': None,
                'source_updated_at': metadata.get('lastupdated'), 'collected_at': now,
                'evidence_version_ids': []})
    return result


def _external_link(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ('https', 'http') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False
