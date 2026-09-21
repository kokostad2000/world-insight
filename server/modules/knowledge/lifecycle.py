"""Recovery-first trash and bounded retention; domain changes stay with their owners."""
import copy
import datetime as dt
import hashlib
import json
import re
import sqlite3
import tempfile
import uuid
from pathlib import Path

from server.platform.errors import ApiError
from .policy_period import first_saved_at, first_collected_at, material_history, material_source_ids, retention_cap, source_histories

KINDS = {'topic', 'evidence', 'claim', 'event', 'observation', 'judgment', 'scenario', 'impact_path', 'review', 'brief'}
ALIASES = {'topics': 'topic', 'claims': 'claim', 'events': 'event', 'metrics': 'observation', 'judgments': 'judgment', 'scenarios': 'scenario', 'impact-paths': 'impact_path', 'reviews': 'review', 'briefs': 'brief'}
DEFAULTS = {'candidate_days': 90, 'candidate_retention_enabled': True, 'batch_limit': 100}
CONTENT = ('excerpt', 'translation', 'content_fingerprint')
ALLOWED = (True, 'excerpt', 'full', 'allowed')


def fail(message, code='invalid_lifecycle', status=400, details=None):
    raise ApiError(status, code, message, details)


def _time(value=None):
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    try:
        parsed = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        fail('时间格式无效')


def _iso(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _latest(snapshots):
    rows = {}
    for entry in snapshots:
        key, row = (entry['kind'], entry['record']['id']), entry['record']
        if key not in rows or rows[key]['version'] < row['version']:
            rows[key] = row
    return rows


def references(record):
    """Yield stable referenced identities at any nesting depth, including old path edges."""
    singular = {'topic_id': 'topic', 'source_id': 'source', 'origin_evidence_id': 'evidence', 'evidence_id': 'evidence', 'judgment_id': 'judgment', 'change_id': 'change'}
    plural = {'topic_ids': 'topic', 'source_ids': 'source', 'claim_ids': 'claim', 'judgment_ids': 'judgment'}
    found = set()
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith('evidence_version_ids') and isinstance(child, list):
                    found.update(('evidence', ref.rsplit('@', 1)[0]) for ref in child if isinstance(ref, str) and '@' in ref)
                elif key in singular and isinstance(child, str) and child:
                    if key != 'source_id' or child != 'manual':
                        found.add((singular[key], child))
                elif key in plural and isinstance(child, list):
                    found.update((plural[key], ref) for ref in child if isinstance(ref, str) and ref)
                elif key == 'judgment_versions' and isinstance(child, list):
                    found.update(('judgment', ref['id']) for ref in child if isinstance(ref, dict) and isinstance(ref.get('id'), str))
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(record)
    return found


def _source_ids(row):
    return {row.get('source_id')} | {channel.get('source_id') for channel in row.get('channels', []) if isinstance(channel, dict)}


def _source_caps(snapshots, sources):
    caps = {}
    for source in [entry['record'] for entry in snapshots if entry['kind'] == 'source'] + list(sources):
        days = source.get('retention_days')
        if days is not None:
            if type(days) is not int or not 1 <= days <= 36500:
                fail('来源保留上限无效，停止清理', 'invalid_source_retention')
            caps[source['id']] = min(days, caps.get(source['id'], days))
    return caps


def evaluate_retention(snapshots, sources, settings=None, now=None):
    """Pure policy evaluator used by maintenance and recovery snapshot sanitization."""
    policy = {**DEFAULTS, **(settings or {})}
    instant, latest = _time(now), _latest(snapshots)
    _source_caps(snapshots, sources)  # Validate all registered nonnull policies first.
    policies_by_source = source_histories(snapshots, sources)
    histories, referenced = {}, set()
    for entry in snapshots:
        kind, row = entry['kind'], entry['record']
        if kind == 'evidence':
            histories.setdefault(row['id'], []).append(row)
        # Activity changes index discoveries; they are not authored research citations.
        if kind in KINDS:
            referenced.update(references(row))
    actions, protected = [], []
    for evidence_id, versions in sorted(histories.items()):
        current = latest[('evidence', evidence_id)]
        timestamps = []
        for row in versions:
            for field in ('first_collected_at', 'collected_at', 'created_at'):
                if row.get(field):
                    try:
                        timestamps.append(_time(row[field]))
                    except ApiError:
                        pass
        if not timestamps:
            protected.append({'id': evidence_id, 'reason': '首次采集时间未知，不能推断到期'})
            continue
        first = min(timestamps)
        provenance = material_history(evidence_id, histories)
        saved_at = first_saved_at(provenance)
        caps = [retention_cap(policies_by_source[source_id], saved_at)
                for source_id in material_source_ids(provenance) if source_id in policies_by_source]
        caps = [cap for cap in caps if cap is not None]
        cap = min(caps) if caps else None
        source_expiry = first_collected_at(provenance) + dt.timedelta(days=cap) if cap is not None else None
        reason = None
        if any(row.get('ingest_origin') != 'collector' for row in versions):
            reason = '人工登记或历史采集来源未知'
        elif any(row.get('manually_touched') or row.get('notes') or row.get('reviewer') or row.get('substantive_confirmed_at') or row.get('restored_at') for row in versions):
            reason = '存在人工修改、注释或确认历史'
        elif ('evidence', evidence_id) in referenced:
            reason = '存在当前或历史研究引用'
        elif any(row.get('status', 'unverified') != 'unverified' for row in versions):
            reason = '存在审阅或处置状态，不能视作未处理候选'
        elif current.get('deleted'):
            reason = '已在回收站，保留用户恢复路径'
        candidate_expiry = first + dt.timedelta(days=policy['candidate_days'])
        candidate_due = not reason and policy['candidate_retention_enabled'] and candidate_expiry <= instant
        source_due = source_expiry is not None and source_expiry <= instant
        needs_redaction = not current.get('content_expired') or any(row.get(field) for row in versions for field in CONTENT)
        if candidate_due or (source_due and needs_redaction):
            use_source = source_due and (not candidate_due or source_expiry <= candidate_expiry)
            actions.append({'kind': 'evidence', 'id': evidence_id, 'expected_version': current['version'],
                'action': 'source_content_expiry' if use_source else 'candidate_expiry',
                'reason': f'来源正文授权期限 {cap} 天已到期' if use_source else f'未引用且无人工处理的采集候选已满 {policy["candidate_days"]} 天',
                'expires_at': _iso(source_expiry if use_source else candidate_expiry),
                'redact_content': True, 'move_to_trash': bool(candidate_due)})
        elif reason:
            protected.append({'id': evidence_id, 'reason': reason})
    actions.sort(key=lambda row: (row['expires_at'], row['id']))
    return {'actions': actions, 'protected': protected, 'evaluated_at': _iso(instant)}


def get_settings(store):
    try:
        return store.get('retention_settings', 'default')
    except ApiError as exc:
        if exc.status != 404:
            raise
        return {**DEFAULTS, 'id': 'default', 'version': 0}


def update_settings(store, body):
    unknown = set(body) - set(DEFAULTS) - {'expected_version'}
    if unknown:
        fail('不支持的保留设置字段')
    if 'candidate_days' in body and (type(body['candidate_days']) is not int or not 1 <= body['candidate_days'] <= 36500):
        fail('候选保留天数须为 1—36500 的整数')
    if 'batch_limit' in body and (type(body['batch_limit']) is not int or not 1 <= body['batch_limit'] <= 200):
        fail('每批上限须为 1—200 的整数')
    if 'candidate_retention_enabled' in body and type(body['candidate_retention_enabled']) is not bool:
        fail('候选清理开关须为布尔值')
    with store.transaction():
        old = get_settings(store)
        _expect(old, body.get('expected_version'))
        data = {key: body.get(key, old[key]) for key in DEFAULTS}
        return store.update('retention_settings', 'default', data, old['version']) if old['version'] else store.create('retention_settings', data, 'default')


def retention_preview(store, now=None):
    with store.transaction():
        result = evaluate_retention(store.snapshots(), store.all('source', include_deleted=True), get_settings(store), now or store.now())
        return {**result, 'settings': get_settings(store), 'total': len(result['actions']), 'physical_content_removal': True}


def _expect(row, version):
    if type(version) is not int:
        fail('须提交整数 expected_version', 'expected_version_required')
    if row['version'] != version:
        fail('版本已变化，请重新预览', 'version_conflict', 409, {'current_version': row['version']})


def _owner(kind):
    from server.modules import knowledge, research, activity
    return knowledge if kind in {'evidence', 'claim', 'event', 'observation'} else activity if kind == 'brief' else research


def run_retention(store, body=None):
    body = body or {}
    if set(body) - {'operation_id'}:
        fail('保留执行仅接受 operation_id；不能改写系统时钟或绕过策略')
    operation_id = body.get('operation_id') or str(uuid.uuid4())
    if not isinstance(operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', operation_id):
        fail('operation_id 格式无效')
    key = 'retention:' + operation_id
    with store.transaction():
        try:
            operation = store.get('lifecycle_operation', key)
        except ApiError as exc:
            if exc.status != 404:
                raise
            preview = retention_preview(store)
            actions = preview['actions'][:get_settings(store)['batch_limit']]
            operation = store.create('lifecycle_operation', {'type': 'retention', 'state': 'running', 'actions': actions}, key)
            results = []
            for action in actions:
                from server.modules import knowledge
                updated = knowledge.expire_content(store, action['id'], action['expected_version'], action['reason'], key + ':' + action['id'])
                if action['move_to_trash']:
                    updated = knowledge.lifecycle_change(store, 'evidence', updated['id'], updated['version'], True, action['reason'])
                results.append({'id': updated['id'], 'version': updated['version'], 'action': action['action'], 'deleted': bool(updated.get('deleted'))})
            operation = store.update('lifecycle_operation', key, {'state': 'compaction_pending' if actions else 'complete', 'results': results, 'remaining': max(0, preview['total'] - len(actions))}, operation['version'])
    pending = [row for row in store.all('lifecycle_operation') if row.get('type') == 'retention' and row.get('state') == 'compaction_pending']
    if pending:
        try:
            store.compact()
        except Exception:
            # A subsequent scheduled batch also retries unfinished compaction.
            return {**operation, 'state': 'compaction_pending', 'error': '正文清理已提交，数据库收缩待重试；使用相同 operation_id 继续', 'operation_id': operation_id}
        with store.transaction():
            for row in pending:
                current = store.get('lifecycle_operation', row['id'])
                if current['state'] == 'compaction_pending':
                    store.update('lifecycle_operation', current['id'], {'state': 'complete'}, current['version'])
            operation = store.get('lifecycle_operation', key)
    return {**operation, 'operation_id': operation_id}


def _targets(body):
    if body.get('cascade') not in (None, False):
        fail('不支持级联删除；请逐项明确选择')
    targets = body.get('targets')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 100:
        fail('须选择 1—100 项明确目标')
    normalized, seen = [], set()
    for target in targets:
        if not isinstance(target, dict):
            fail('删除目标格式无效')
        kind = ALIASES.get(target.get('kind'), target.get('kind'))
        record_id, version = target.get('id'), target.get('expected_version')
        if kind not in KINDS or not isinstance(record_id, str) or not record_id or type(version) is not int:
            fail('删除目标须含受支持 kind、id 和 expected_version')
        if (kind, record_id) in seen:
            fail('删除目标重复')
        seen.add((kind, record_id))
        normalized.append({'kind': kind, 'id': record_id, 'expected_version': version})
    return sorted(normalized, key=lambda row: (row['kind'], row['id']))


def _graph(snapshots, targets):
    latest, ids = _latest(snapshots), {(row['kind'], row['id']) for row in targets}
    for target in targets:
        row = latest.get((target['kind'], target['id']))
        if row is None:
            fail('目标不存在', 'not_found', 404)
        _expect(row, target['expected_version'])
        if row.get('deleted'):
            fail('目标已在回收站', 'already_deleted', 409)
    affected = []
    for entry in snapshots:
        row = entry['record']
        refs = references(row).intersection(ids)
        if refs and entry['kind'] in KINDS | {'change', 'notification'} and (entry['kind'], row['id']) not in ids:
            affected.append({'kind': entry['kind'], 'id': row['id'], 'version': row['version'], 'current_version': latest[(entry['kind'], row['id'])]['version'], 'references': [list(ref) for ref in sorted(refs)]})
    # Hash all target history and all dependent histories; compare permissions at commit too.
    relevant = ids | {(row['kind'], row['id']) for row in affected}
    raw = [entry for entry in snapshots if (entry['kind'], entry['record']['id']) in relevant]
    source_ids = {source_id for entry in raw for source_id in _source_ids(entry['record']) if source_id not in (None, 'manual')}
    source_caps = _source_caps(snapshots, [])
    permissions = [{'id': source_id, 'rights': latest.get(('source', source_id), {}).get('rights'), 'retention_days': source_caps.get(source_id)} for source_id in sorted(source_ids)]
    raw.sort(key=lambda entry: (entry['kind'], entry['record']['id'], entry['record']['version']))
    affected.sort(key=lambda row: (row['kind'], row['id'], row['version']))
    return {'targets': targets, 'dependencies': affected, 'plan_hash': _hash({'records': raw, 'permissions': permissions})}


def deletion_preview(store, body):
    targets = _targets(body)
    with store.transaction():
        graph = _graph(store.snapshots(), targets)
        return store.create('lifecycle_plan', {**graph, 'state': 'previewed', 'expires_at': _iso(_time(store.now()) + dt.timedelta(minutes=30)),
            'mode': 'recoverable_trash', 'cascade': False, 'history_preserved': True,
            'warning': '记录将进入回收站；历史与引用保留。来源授权到期正文不会通过恢复重新出现。'})


def _valid_plan(store, plan_id):
    plan = store.get('lifecycle_plan', plan_id)
    if _time(plan['expires_at']) <= _time(store.now()):
        fail('删除预览已过期，请重新预览', 'plan_expired', 409)
    graph = _graph(store.snapshots(), plan['targets'])
    if graph['plan_hash'] != plan['plan_hash']:
        fail('目标、引用或来源权限已变化，请重新预览', 'plan_changed', 409)
    return plan


def _export(snapshots, targets):
    from .rights import build_policy_context, present_evidence
    latest = _latest(snapshots)
    context = build_policy_context(snapshots)
    included = {(row['kind'], row['id']) for row in targets}
    # Include incoming authored dependencies, then their full outgoing history graph.
    for entry in snapshots:
        if entry['kind'] in KINDS and references(entry['record']).intersection(included):
            included.add((entry['kind'], entry['record']['id']))
    while True:
        expanded = included | {ref for entry in snapshots if (entry['kind'], entry['record']['id']) in included for ref in references(entry['record']) if ref[0] in KINDS | {'source'}}
        if expanded == included:
            break
        included = expanded
    output, omissions = [], []
    for entry in snapshots:
        kind, row = entry['kind'], copy.deepcopy(entry['record'])
        if (kind, row['id']) not in included:
            continue
        if kind == 'evidence':
            row = present_evidence(row, context, action='export')
            # Never create another body copy with a finite source deadline.
            if not row['content_policy']['content_allowed'] or row['content_policy']['retention_days'] is not None:
                for field in CONTENT:
                    row[field] = None if field == 'content_fingerprint' else ''
                row['export_content_omitted'] = True
                omissions.append({'id': row['id'], 'version': row['version'], 'reason': '权限受限、内容到期或来源设有保留上限'})
        if kind == 'source':
            public_fields = {'id', 'version', 'created_at', 'updated_at', 'name', 'adapter', 'domain', 'license_url', 'checked_at', 'rights', 'retention_days'}
            row = {key: value for key, value in row.items() if key in public_fields}
        output.append({'kind': kind, 'record': row})
    return {'format': 'world-insight-lifecycle-export-v1', 'mode': 'recoverable_trash', 'snapshots': output, 'content_omissions': omissions, 'credentials_included': False}


def _config(store):
    from server.platform.config import load_config
    config = load_config(root=Path(__file__).resolve().parents[3], data_dir=store.data_dir)
    config['db_path'] = store.path
    return config


def prepare_recovery(store, plan_id):
    from ops.backup import create_backup, sha256, unpack_verified
    from ops.runtime import atomic_json, OpsError
    with store.transaction():
        plan = _valid_plan(store, plan_id)
    recovery_id = str(uuid.uuid4())
    config = _config(store)
    output = config['backup_dir'] / ('deletion-' + recovery_id + '.wibackup')
    export_path = output.with_suffix('.json')
    try:
        create_backup(config, output=output, label='before-trash')
        with tempfile.TemporaryDirectory(prefix='world-insight-delete-verify-') as temporary:
            manifest = unpack_verified(output, temporary)
            with sqlite3.connect(f'file:{Path(temporary) / "world-insight.sqlite"}?mode=ro', uri=True) as db:
                snapshots = [{'kind': kind, 'record': json.loads(raw)} for kind, raw in db.execute('SELECT kind,data FROM versions')]
            # Backup sanitizer may omit body fields. Identity and every target version must survive.
            latest = _latest(snapshots)
            for target in plan['targets']:
                _expect(latest[(target['kind'], target['id'])], target['expected_version'])
        with store.transaction():
            _valid_plan(store, plan_id)
            exported = _export(store.snapshots(), plan['targets'])
        atomic_json(export_path, exported)
        receipt = {'id': recovery_id, 'backup_path': str(output), 'backup_sha256': sha256(output), 'export_path': str(export_path), 'export_sha256': sha256(export_path), 'instance_id': manifest['instance_id'], 'content_omissions': len(exported['content_omissions']), 'verified': True}
        with store.transaction():
            plan = _valid_plan(store, plan_id)
            return store.update('lifecycle_plan', plan_id, {'state': 'recovery_ready', 'recovery': receipt}, plan['version'])
    except (OpsError, OSError, KeyError) as exc:
        fail('恢复包或导出验证失败，未删除任何记录', 'recovery_failed', 503)


def _verify_recovery(store, plan):
    from ops.backup import sha256, validate_backup
    from ops.runtime import OpsError
    receipt = plan.get('recovery')
    if not receipt or not receipt.get('verified'):
        fail('请先创建并验证恢复包与导出', 'recovery_required', 409)
    try:
        if sha256(receipt['backup_path']) != receipt['backup_sha256'] or sha256(receipt['export_path']) != receipt['export_sha256']:
            raise OSError('changed')
        manifest = validate_backup(receipt['backup_path'])
        identity = json.loads((store.data_dir / 'instance.json').read_text())
        if manifest['instance_id'] != receipt['instance_id'] or receipt['instance_id'] != identity['instance_id']:
            raise OSError('wrong instance')
    except (OpsError, OSError, ValueError, KeyError):
        fail('恢复包、导出或实例校验不通过，未删除记录', 'recovery_invalid', 409)


def commit_deletion(store, plan_id, body):
    if body.get('confirm') is not True or not isinstance(body.get('reason'), str) or not body['reason'].strip():
        fail('须明确 confirm=true 并填写删除原因')
    plan = store.get('lifecycle_plan', plan_id)
    if body.get('plan_hash') != plan['plan_hash'] or body.get('recovery_id') != plan.get('recovery', {}).get('id') or body.get('expected_versions') != plan['targets']:
        fail('须确认本次预览、恢复包和每项目标版本', 'confirmation_mismatch', 409)
    if plan['state'] == 'committed':
        return plan
    _verify_recovery(store, plan)
    with store.transaction():
        plan = _valid_plan(store, plan_id)
        results = []
        # Owners may mark other selected targets for review; preserve that update while
        # deleting the selected set in the same transaction after the full graph check.
        for target in plan['targets']:
            current = store.get(target['kind'], target['id'])
            row = _owner(target['kind']).lifecycle_change(store, target['kind'], target['id'], current['version'], True, body['reason'].strip())
            results.append({'kind': target['kind'], 'id': row['id'], 'version': row['version']})
        return store.update('lifecycle_plan', plan_id, {'state': 'committed', 'results': results, 'committed_at': store.now()}, plan['version'])


def trash(store, query):
    kind = ALIASES.get(query.get('kind'), query.get('kind'))
    if kind is not None and kind not in KINDS:
        fail('回收站类型无效')
    try:
        limit, offset = min(200, max(1, int(query.get('limit', 100)))), max(0, int(query.get('offset', 0)))
    except (ValueError, TypeError):
        fail('分页参数无效')
    rows = [{'kind': selected, 'id': row['id'], 'version': row['version'], 'title': row.get('title') or row.get('question') or row.get('conclusion') or row.get('statement') or selected,
        'deleted_at': row.get('deleted_at'), 'deleted_reason': row.get('deleted_reason'), 'content_expired': bool(row.get('content_expired')), 'recoverable': True}
        for selected in ([kind] if kind else sorted(KINDS)) for row in store.all(selected, include_deleted=True) if row.get('deleted')]
    rows.sort(key=lambda row: (row['deleted_at'] or '', row['id']), reverse=True)
    return {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit, 'data_status': 'fresh', 'empty_reason': None if rows else 'no_matches'}


def restore(store, kind, record_id, body):
    kind = ALIASES.get(kind, kind)
    if kind not in KINDS:
        fail('恢复类型无效')
    if not isinstance(body.get('reason'), str) or not body['reason'].strip():
        fail('请填写恢复原因')
    with store.transaction():
        row = store.get(kind, record_id)
        _expect(row, body.get('expected_version'))
        if not row.get('deleted'):
            fail('记录未在回收站', 'not_deleted', 409)
        return _owner(kind).lifecycle_change(store, kind, record_id, row['version'], False, body['reason'].strip())


def handle(store, method, segments, body, query):
    if segments == ['retention']:
        return get_settings(store) if method == 'GET' else update_settings(store, body) if method == 'PATCH' else None
    if segments == ['retention', 'preview'] and method == 'GET':
        result = retention_preview(store)
        return {**result, 'actions': result['actions'][:200], 'protected': result['protected'][:200], 'truncated': result['total'] > 200}
    if segments == ['retention', 'run'] and method == 'POST':
        return run_retention(store, body)
    if segments == ['deletions', 'preview'] and method == 'POST':
        return deletion_preview(store, body)
    if len(segments) == 3 and segments[0] == 'deletions' and method == 'POST':
        if segments[2] == 'prepare-recovery':
            return prepare_recovery(store, segments[1])
        if segments[2] == 'commit':
            return commit_deletion(store, segments[1], body)
    if segments == ['trash'] and method == 'GET':
        return trash(store, query)
    if len(segments) == 4 and segments[0] == 'trash' and segments[3] == 'restore' and method == 'POST':
        return restore(store, segments[1], segments[2], body)
    return None
