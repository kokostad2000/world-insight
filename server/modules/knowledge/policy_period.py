"""Pure policy-period selection shared by reads, retention and recovery copies."""
import datetime as dt


def _time(value):
    try:
        parsed = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def first_saved_at(versions):
    """Earliest immutable persistence fact; editable collection dates cannot renew it."""
    versions = list(versions)
    earliest = {}
    for row in versions:
        key = row.get('id')
        if key not in earliest or row.get('version', 0) < earliest[key].get('version', 0):
            earliest[key] = row
    if any(not any(_time(row.get(field)) for field in ('first_collected_at', 'created_at')) for row in earliest.values()):
        return None
    times = [_time(row.get(field)) for row in versions for field in ('first_collected_at', 'created_at')]
    times = [value for value in times if value is not None]
    return min(times) if times else None


def first_collected_at(versions):
    times = [_time(row.get(field)) for row in versions for field in ('first_collected_at', 'collected_at', 'created_at')]
    times = [value for value in times if value is not None]
    return min(times) if times else None


def material_history(evidence_id, histories):
    """Historical original links cannot reset a copied material's source term."""
    result, seen, pending = [], set(), [evidence_id]
    while pending:
        record_id = pending.pop()
        if record_id in seen:
            continue
        seen.add(record_id)
        rows = histories.get(record_id, [])
        result.extend(rows)
        pending.extend(row['origin_evidence_id'] for row in rows if row.get('origin_evidence_id'))
    return result


def material_source_ids(versions):
    return {row.get('source_id') for row in versions} | {channel.get('source_id') for row in versions for channel in row.get('channels', []) if isinstance(channel, dict)}


def applicable_source_versions(history, saved_at):
    """Select the licence in force when saved plus every later restriction.

    Superseded pre-material defaults are irrelevant to a newly saved material.
    Unknown or non-monotonic version timestamps retain all history conservatively.
    Equal timestamps straddling a save are ambiguous, so all tied versions apply.
    Inputs, including historical policy values, are never rewritten.
    """
    history = list(history)
    start = _time(saved_at)
    if start is None or len(history) < 2:
        return history
    dated = [(row, _time(row.get('updated_at') or (row.get('created_at') if row.get('version', 1) == 1 else None))) for row in history]
    if any(stamp is None for _, stamp in dated):
        return history
    ordered = sorted(dated, key=lambda item: item[0].get('version', 0))
    if any(earlier[1] > later[1] for earlier, later in zip(ordered, ordered[1:])):
        return history
    before = [stamp for _, stamp in dated if stamp < start]
    boundary = max(before) if before else start
    return [row for row, stamp in dated if stamp >= boundary]


def source_histories(snapshots, sources=None):
    result = {}
    for entry in snapshots:
        if entry['kind'] == 'source':
            result.setdefault(entry['record']['id'], []).append(entry['record'])
    for source in sources or []:
        result.setdefault(source['id'], []).append(source)
    return result


def retention_cap(history, saved_at):
    values = [row.get('retention_days') for row in applicable_source_versions(history, saved_at) if row.get('retention_days') is not None]
    if any(type(days) is not int or not 1 <= days <= 36500 for days in values):
        raise ValueError('Invalid source retention policy')
    return min(values) if values else None
