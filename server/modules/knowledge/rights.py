"""Pure evidence access policy shared by reads, citations and ordinary exports.

Build a fresh context from ALL immutable Store snapshots once per request, within
the same transaction as the records being presented. Never cache it across writes
or requests: permission changes and the passage of time both affect access.

The returned rights are conservative scope intersections: False, metadata, excerpt,
or full. True/allowed mean a registered unrestricted grant; absent/unknown/invalid
values never grant body access. This module changes no persistent record and is
not the backup policy (ordinary exports may include unexpired licensed content).
"""
import copy
import datetime as dt

from .lifecycle import evaluate_retention
from .policy_period import applicable_source_versions, first_saved_at, source_histories


ACTIONS = ('fetch', 'store', 'display', 'export', 'ai')
CONTENT_FIELDS = ('excerpt', 'translation', 'content_fingerprint')
SCOPES = (False, 'metadata', 'excerpt', 'full')


def _rank(value):
    if value is True or value in ('full', 'allowed'):
        return 3
    if value == 'excerpt':
        return 2
    if value in ('metadata', 'link_only'):
        return 1
    return 0


def _grants(row):
    rights = row.get('rights')
    return {action: _rank(rights.get(action)) if isinstance(rights, dict) else 0 for action in ACTIONS}


def _instant(value):
    try:
        parsed = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def _iso(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z') if value else None


def _source_ids(row):
    # An unregistered URL-only channel is unknown, not a newly granted licence.
    found = {row.get('source_id')}
    for channel in row.get('channels') or []:
        found.add(channel.get('source_id') if isinstance(channel, dict) else None)
    return found


def _reason(code, message, **details):
    return {'code': code, 'reason': message, **details}


def build_policy_context(snapshots, sources=None, settings=None, now=None):
    """Index full history and evaluate retention once; inputs are never mutated.

    ``sources`` optionally supplies additional/current source records. Historical
    source restrictions remain applicable even after a later grant or a removed
    channel. Only the built-in ``manual`` alias may lack a Source registry record.
    Invalid retention policy raises the lifecycle ApiError before any content is
    returned. A finite policy with no reliable collection time fails closed.
    """
    snapshots, sources = list(snapshots), list(sources or [])
    latest, evidence_history = {}, {}
    for entry in snapshots:
        kind, row = entry['kind'], entry['record']
        key = (kind, row['id'])
        if key not in latest or latest[key]['version'] < row['version']:
            latest[key] = row
        if kind == 'evidence':
            evidence_history.setdefault(row['id'], []).append(row)
    source_history = source_histories(snapshots, sources)
    policy = settings if settings is not None else latest.get(('retention_settings', 'default'))
    retention = evaluate_retention(snapshots, sources, policy, now)
    observed_at = _instant(retention['evaluated_at'])
    due = {action['id']: action for action in retention['actions']}
    source_policies = {}
    for source_id, history in source_history.items():
        source_policies[source_id] = [{key: copy.deepcopy(row.get(key)) for key in ('id', 'created_at', 'updated_at', 'retention_days',
            'recovery_policy_id', 'policy_effective_at', 'policy_end_at', 'restored_at')} | {'version': row.get('version') or 0, 'grants': _grants(row)} for row in history]
    evidence_policies = {}
    for evidence_id, history in evidence_history.items():
        current = latest[('evidence', evidence_id)]
        source_ids = set().union(*(_source_ids(row) for row in history))
        timestamps = [_instant(row.get(field)) for row in history for field in ('first_collected_at', 'collected_at', 'created_at')]
        timestamps = [stamp for stamp in timestamps if stamp is not None]
        evidence_policies[evidence_id] = {
            'version': current['version'], 'grants': _grants(current),
            'status': current.get('status'), 'deleted': bool(current.get('deleted')),
            'content_expired': any(row.get('content_expired') for row in history),
            'source_ids': source_ids, 'first_collected_at': min(timestamps) if timestamps else None,
            'first_saved_at': first_saved_at(history),
            'origins': {row['origin_evidence_id'] for row in history if row.get('origin_evidence_id')},
            'due': copy.deepcopy(due.get(evidence_id)),
        }
    # Return only policy facts: contexts never carry licensed body or user notes.
    return {'sources': source_policies, 'evidence': evidence_policies, 'evaluated_at': retention['evaluated_at'], 'now': observed_at}


def _provenance(record, context):
    """Collect historical provenance, including old transitive original links."""
    source_ids, failures, visited, policies = set(), [], set(), []
    todo = [(record['id'], frozenset())]
    while todo:
        evidence_id, ancestors = todo.pop()
        if evidence_id in ancestors:
            failures.append(_reason('invalid_provenance', '原始出处关系存在循环，无法确认有效许可'))
            continue
        if evidence_id in visited:
            continue
        visited.add(evidence_id)
        policy = context['evidence'].get(evidence_id)
        if policy is None:
            failures.append(_reason('missing_evidence_policy', '材料或原始出处缺少完整权限历史', evidence_id=evidence_id))
            continue
        policies.append((evidence_id, policy))
        source_ids.update(policy['source_ids'])
        todo.extend((origin, ancestors | {evidence_id}) for origin in sorted(policy['origins']))
    return source_ids, failures, policies


def effective_policy(record, context, action='display'):
    """Return effective scopes, expiry and explicit reasons for one version.

    Evidence grants intersect the requested version with the latest version;
    source grants and shortest source limits intersect all historical provenance.
    A full-body record requires full permission; an excerpt grant cannot silently
    disclose a body marked ``content_scope=full``. The manual alias still requires
    explicit evidence grants. Unknown action/context/version fails closed.
    """
    if action not in ACTIONS:
        raise ValueError('Unsupported evidence content action')
    current = context['evidence'].get(record['id'])
    requested = _grants(record)
    grants = dict(requested)
    reasons, limiters = [], {name: [] for name in ACTIONS}
    required = 3 if record.get('content_scope') == 'full' else 2
    if record.get('content_scope', 'excerpt') not in ('excerpt', 'full'):
        reasons.append(_reason('unknown_content_scope', '正文范围未知，不能推定摘录授权覆盖全部内容'))
    if current is None or record.get('version', 0) > current['version']:
        reasons.append(_reason('missing_current_policy', '权限上下文缺少材料最新版本，须重新读取'))
        grants = {name: 0 for name in ACTIONS}
    else:
        for name in ACTIONS:
            grants[name] = min(grants[name], current['grants'][name])
            if requested[name] < required:
                limiters[name].append(_reason('evidence_rights', '请求材料版本未授权此正文范围', version=record.get('version'), action=name, scope=SCOPES[requested[name]]))
            if current['grants'][name] < required:
                limiters[name].append(_reason('current_evidence_rights', '材料当前版本的权限仍适用于历史内容', version=current['version'], action=name, scope=SCOPES[current['grants'][name]]))
        if current['status'] == 'restricted' or record.get('status') == 'restricted':
            reasons.append(_reason('restricted_status', '材料当前或请求版本标记为受限'))
        if current['deleted'] or record.get('deleted'):
            reasons.append(_reason('deleted', '材料已进入回收站，正文暂不可访问；人工注释与引用保留'))
    source_ids, provenance_failures, provenance = _provenance(record, context)
    reasons.extend(provenance_failures)
    for evidence_id, ancestor in provenance:
        if evidence_id == record['id']:
            continue
        for name in ACTIONS:
            grants[name] = min(grants[name], ancestor['grants'][name])
            if ancestor['grants'][name] < required:
                limiters[name].append(_reason('origin_evidence_rights', '原始出处材料的当前权限限制转引正文', evidence_id=evidence_id, action=name, scope=SCOPES[ancestor['grants'][name]]))
        if ancestor['status'] == 'restricted':
            reasons.append(_reason('origin_restricted', '原始出处材料当前标记为受限', evidence_id=evidence_id))
    # Include this snapshot's provenance even if a caller supplies stale context.
    source_ids.update(_source_ids(record))
    saved_times = [row['first_saved_at'] for _, row in provenance]
    saved_at = min(saved_times) if saved_times and all(saved_times) else None
    caps, source_versions, recovery_constraints = [], {}, []
    for source_id in sorted(source_ids, key=lambda value: str(value)):
        history = context['sources'].get(source_id)
        if history is None:
            if source_id != 'manual':
                reasons.append(_reason('missing_source_policy', '来源许可未登记或渠道来源未知，不能推定允许正文', source_id=source_id))
                grants = {name: 0 for name in ACTIONS}
            continue
        policies = applicable_source_versions(history, saved_at)
        recovery_constraints.extend({'id': row['recovery_policy_id'], 'source_id': source_id, 'source_version': row['version'],
            'policy_effective_at': row['policy_effective_at'], 'policy_end_at': row['policy_end_at'],
            'retention_days': row['retention_days'], 'rights': {name: SCOPES[value] for name, value in row['grants'].items()},
            'reason': '恢复时保留了原库的来源正文约束；后续人工重新核对只适用于新材料，旧材料的期限和限制不重置'}
            for row in policies if row.get('recovery_policy_id'))
        source_versions[source_id] = sorted({row['version'] for row in policies})
        caps.extend(row['retention_days'] for row in policies if row['retention_days'] is not None)
        current_source_version = max(row['version'] or 0 for row in history)
        for name in ACTIONS:
            limiting = min(policies, key=lambda row: (row['grants'][name], row['version'] or 0))
            source_grant = limiting['grants'][name]
            grants[name] = min(grants[name], source_grant)
            if source_grant < required:
                historical = (limiting['version'] or 0) < current_source_version
                recovered = bool(limiting.get('recovery_policy_id'))
                limiters[name].append(_reason('recovery_source_rights' if recovered else ('historical_source_rights' if historical else 'source_rights'),
                    '恢复时保留的来源许可限制正文访问，请核对来源恢复约束' if recovered else ('材料保存期间来源历史版本的较严许可仍适用' if historical else '来源登记许可限制正文访问'),
                    source_id=source_id, version=limiting['version'], action=name, scope=SCOPES[source_grant]))
    cap = min(caps) if caps else None
    timestamps = [row['first_collected_at'] for _, row in provenance if row['first_collected_at']]
    first = min(timestamps) if timestamps else None
    source_expires_at = first + dt.timedelta(days=cap) if first and cap is not None else None
    expired = bool(record.get('content_expired') or any(row['content_expired'] for _, row in provenance))
    expiry = source_expires_at
    if cap is not None and (first is None or saved_at is None):
        reasons.append(_reason('unknown_retention_start', '来源有正文期限，但首次保存时间未知，无法确认仍在许可期内'))
    if source_expires_at and source_expires_at <= context['now']:
        expired = True
        reasons.append(_reason('source_content_expiry', '历史来源/渠道中最短正文保留期限已到期', retention_days=cap, expires_at=_iso(source_expires_at)))
    if current and current['due']:
        due = current['due']
        expired = True
        due_at = _instant(due['expires_at'])
        expiry = min(expiry, due_at) if expiry else due_at
        reasons.append(_reason(due['action'], due['reason'], expires_at=due['expires_at']))
    if expired and not any(item['code'].endswith('expiry') for item in reasons):
        reasons.append(_reason('content_expired', '正文已被标记到期，旧版本不能恢复访问'))
    relevant = ('store',) if action == 'store' else ('store', action)
    for name in relevant:
        reasons.extend(limiters[name])
    # De-duplicate identical explanations without mutating the indexed policy.
    unique = []
    for reason in reasons:
        if reason not in unique:
            unique.append(copy.deepcopy(reason))
    allowed = not unique and all(grants[name] >= required for name in relevant) and not expired
    return {'rights': {name: SCOPES[rank] for name, rank in grants.items()},
        'content_allowed': allowed, 'content_expired': expired, 'content_expires_at': _iso(expiry),
        'retention_days': cap, 'source_ids': sorted(item for item in source_ids if isinstance(item, str)),
        'source_policy_versions': source_versions, 'recovery_constraints': recovery_constraints,
        'action': action, 'evaluated_at': context['evaluated_at'], 'reasons': unique}


def strip_licensed_content(record):
    """Pure content-only removal, including known legacy channel copies.

    Authored notes, metadata titles and provenance survive. Channels have never
    been a second body storage API; only the three recognized body fields change.
    """
    item = copy.deepcopy(record)
    for field in CONTENT_FIELDS:
        item[field] = None if field == 'content_fingerprint' else ''
    for channel in item.get('channels') or []:
        if isinstance(channel, dict):
            for field in CONTENT_FIELDS:
                if field in channel:
                    channel[field] = None if field == 'content_fingerprint' else ''
    return item


def present_evidence(record, context, action='display'):
    """Return an independent sanitized view, preserving notes and exact version IDs.

    ``rights`` remains the declared per-record licence, for truthful history;
    ``effective_rights``/``content_policy`` state the access decision. This routine
    does not redact authored notes, assertions, titles or research references.
    """
    item = copy.deepcopy(record)
    policy = effective_policy(record, context, action)
    item['version_id'] = f'{record["id"]}@{record["version"]}'
    item['effective_rights'] = policy['rights']
    item['content_expires_at'] = policy['content_expires_at']
    item['content_policy'] = policy
    if not policy['content_allowed']:
        item = strip_licensed_content(item)
        item['content_restricted'] = True
        if action == 'export':
            item['export_content_omitted'] = True
    if policy['content_expired']:
        item['content_expired'] = True
    return item
