"""M3: immutable evidence, attributed claims, events and observations."""
import copy
import hashlib
import json
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from server.platform.errors import ApiError
from .validation import choice, expected, fail, fields, page, references, strings, temporal, text, topic

COLLECTIONS = {"evidence": "evidence", "claims": "claim", "events": "event", "metrics": "observation"}
EVIDENCE_FIELDS = {"source_id", "url", "source_record_id", "title", "excerpt", "language", "publisher", "author", "material_type", "published_at", "source_updated_at", "collected_at", "discovered_at", "status", "origin_evidence_id", "channels", "content_fingerprint", "rights", "topic_id", "topic_ids", "notes", "translation", "change_reason", "is_fixture", "provider_seen_at"}
CLAIM_FIELDS = {"subject", "statement", "evidence_version_ids", "attribution", "dispute_status", "topic_id", "notes", "change_reason", "is_fixture"}
EVENT_FIELDS = {"title", "event_type", "actors", "occurred_at", "time_precision", "location", "claim_ids", "evidence_version_ids", "verification_status", "topic_id", "notes", "change_reason", "is_fixture"}
METRIC_FIELDS = {"indicator", "country_code", "value", "unit", "period", "published_at", "frequency", "source_id", "evidence_version_ids", "topic_id", "notes", "change_reason", "is_fixture"}
EVIDENCE_STATUSES = {"unverified", "reviewed", "disputed", "corrected", "withdrawn", "inaccessible", "restricted"}


def canonical_url(value):
    if not value:
        return None
    text(value, "url", True)
    try:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            fail("原始链接须为不含凭据的 HTTP(S) URL")
        port = parts.port
    except ValueError:
        fail("原始链接格式无效")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port is None or (parts.scheme == "https" and port == 443) or (parts.scheme == "http" and port == 80) else f"{host}:{port}"
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", urlencode(sorted(params)), ""))


def _rights(value):
    defaults = {"fetch": False, "store": "metadata", "display": "metadata", "export": "metadata", "ai": False}
    if value is None:
        return defaults
    if not isinstance(value, dict) or set(value) - set(defaults):
        fail("rights 须包含 fetch/store/display/export/ai 授权范围")
    result = {**defaults, **value}
    for key, permission in result.items():
        if permission not in (True, False, None, "none", "metadata", "link_only", "excerpt", "full", "allowed", "unknown"):
            fail(f"rights.{key} 授权范围无效")
    return result


def _excerpt_allowed(rights, action):
    return rights.get(action) in (True, "excerpt", "full", "allowed")


def _channel(data):
    return {"source_id": data.get("source_id"), "source_record_id": data.get("source_record_id"), "url": data.get("url"), "publisher": data.get("publisher"), "discovered_at": data.get("discovered_at"), "title": data.get("title")}


def _channel_key(value):
    return value.get("source_id"), value.get("source_record_id"), canonical_url(value.get("url"))


def _channels(values):
    result, keys = [], set()
    if not isinstance(values, list):
        fail("channels 须为列表")
    for value in values:
        if isinstance(value, str):
            value = {"url": value}
        if not isinstance(value, dict):
            fail("渠道须为对象")
        value = {k: value.get(k) for k in ("source_id", "source_record_id", "url", "publisher", "discovered_at", "title")}
        if value.get("url"):
            canonical_url(value["url"])
        key = _channel_key(value)
        if key not in keys:
            keys.add(key)
            result.append(value)
    return result


def _prepare_evidence(store, data, old=None):
    defaults = {"source_id": "manual", "url": None, "source_record_id": None, "title": "", "excerpt": "", "language": "unknown", "publisher": None, "author": None, "material_type": "article", "published_at": None, "source_updated_at": None, "collected_at": store.now(), "discovered_at": store.now(), "status": "unverified", "origin_evidence_id": None, "channels": [], "rights": _rights(None), "topic_id": None, "topic_ids": [], "notes": "", "translation": "", "change_reason": "初次登记", "is_fixture": False}
    item = {**defaults, **(old or {}), **data}
    item["title"] = text(item["title"], "title", True)
    text(item["excerpt"], "excerpt")
    item["excerpt"] = item["excerpt"] or ""
    item["url"] = canonical_url(item["url"])
    item["rights"] = _rights(item["rights"])
    if item["excerpt"] and not _excerpt_allowed(item["rights"], "store"):
        fail("来源授权未允许保存摘录；请仅登记链接或先核对授权", "rights_restricted")
    for key in ("published_at", "source_updated_at", "collected_at", "discovered_at", "provider_seen_at"):
        item.setdefault(key, None)
        item[key] = temporal(item[key], key)
    item["status"] = choice(item["status"], EVIDENCE_STATUSES, "status")
    item["topic_id"] = topic(store, item["topic_id"])
    item["topic_ids"] = strings(item.get("topic_ids", []), "topic_ids")
    if item["topic_id"] and item["topic_id"] not in item["topic_ids"]:
        item["topic_ids"].append(item["topic_id"])
    for topic_id in item["topic_ids"]:
        topic(store, topic_id)
    if item["origin_evidence_id"]:
        origin = store.get("evidence", item["origin_evidence_id"])
        seen = {old["id"]} if old else set()
        while origin:
            if origin["id"] in seen:
                fail("原始出处关系不能循环")
            seen.add(origin["id"])
            origin = store.get("evidence", origin["origin_evidence_id"]) if origin.get("origin_evidence_id") else None
    item["channels"] = _channels(item["channels"] or [_channel(item)])
    # Fingerprints only cover permitted nonempty stored excerpts. Titles never establish identity.
    item["content_fingerprint"] = hashlib.sha256(item["excerpt"].encode()).hexdigest() if item["excerpt"] else None
    return {k: v for k, v in item.items() if k in EVIDENCE_FIELDS}


def _event_payload(record, reason=None, **extra):
    return {"topic_id": record.get("topic_id"), "topic_ids": record.get("topic_ids", []), "title": record.get("title") or record.get("statement"), "version": record["version"], "version_id": f'{record["id"]}@{record["version"]}', "evidence_id": record["id"], "evidence_version_ids": record.get("evidence_version_ids", []), "occurred_at": record.get("occurred_at"), "reason": reason, **extra}


def _present(record, action="display"):
    item = copy.deepcopy(record)
    if item.get("rights"):
        if not _excerpt_allowed(item["rights"], action) or item.get("status") == "restricted":
            item["excerpt"], item["translation"] = "", ""
            item["content_restricted"] = True
    if "content_fingerprint" in item:
        item["version_id"] = f'{item["id"]}@{item["version"]}'
    return item


def _alias_keys(data):
    keys = []
    if data.get("source_record_id"):
        keys.append("source:" + json.dumps([data.get("source_id"), data["source_record_id"]], ensure_ascii=False))
    if data.get("url"):
        keys.append("url:" + canonical_url(data["url"]))
    return keys


def _alias_id(key):
    return hashlib.sha256(key.encode()).hexdigest()


def _bind_aliases(store, record):
    for channel in [record] + record.get("channels", []):
        for key in _alias_keys(channel):
            alias_id = _alias_id(key)
            try:
                old = store.get("evidence_alias", alias_id)
            except ApiError as error:
                if error.status != 404:
                    raise
                store.create("evidence_alias", {"key": key, "evidence_id": record["id"]}, record_id=alias_id)
            else:
                if old["evidence_id"] != record["id"]:
                    store.update("evidence_alias", alias_id, {"evidence_id": record["id"]}, old["version"])


def _dedup(store, data):
    for key in _alias_keys(data):
        try:
            alias = store.get("evidence_alias", _alias_id(key))
            item = store.get("evidence", alias["evidence_id"])
        except ApiError as error:
            if error.status == 404:
                continue
            raise
        distinct_source_records = data.get("source_id") == item.get("source_id") and data.get("source_record_id") and item.get("source_record_id") and data["source_record_id"] != item["source_record_id"]
        if not distinct_source_records:
            return item
    if data.get("source_record_id"):
        for item in store.find("evidence", "source_record_id", data["source_record_id"]):
            if item.get("source_id") == data.get("source_id"):
                return item
    if data.get("url"):
        for item in store.find("evidence", "url", data["url"]):
            distinct_source_records = data.get("source_id") == item.get("source_id") and data.get("source_record_id") and item.get("source_record_id") and data["source_record_id"] != item["source_record_id"]
            if not distinct_source_records:
                return item
    if data.get("content_fingerprint"):
        for item in store.find("evidence", "content_fingerprint", data["content_fingerprint"]):
            if not item.get("split_from") and not item.get("split_children"):
                return item
    return None


def ingest(store, data):
    """Public acquisition boundary. Exact identity, immutable updates, no semantic confirmation."""
    clean = fields(data, EVIDENCE_FIELDS)
    with store.transaction():
        item = _prepare_evidence(store, clean)
        old = _dedup(store, item)
        if old:
            channels = _channels(old.get("channels", []) + item["channels"])
            topics = list(dict.fromkeys(old.get("topic_ids", []) + ([old["topic_id"]] if old.get("topic_id") else []) + item["topic_ids"]))
            patch = {"channels": channels, "topic_ids": topics}
            same_identity = (item.get("url") and item["url"] == old.get("url")) or (item.get("source_record_id") and item["source_record_id"] == old.get("source_record_id") and item["source_id"] == old.get("source_id"))
            tracked = ("title", "excerpt", "source_updated_at", "published_at")
            changed = same_identity and any(item.get(k) != old.get(k) for k in tracked if k in clean)
            if changed:
                patch.update({k: item[k] for k in tracked + ("content_fingerprint",) if k in clean or k == "content_fingerprint"})
                patch["change_reason"] = "已接入字段变化，待人工判断是否为实质更正"
                patch["change_candidate"] = True
                content = item["excerpt"] if "excerpt" in clean else old.get("excerpt", "")
                patch["content_fingerprint"] = hashlib.sha256(content.encode()).hexdigest() if content else None
            if all(old.get(k) == v for k, v in patch.items()):
                _bind_aliases(store, old)
                return {**_present(old), "deduplicated": True}
            updated = store.update("evidence", old["id"], patch, old["version"])
            _bind_aliases(store, updated)
            store.publish("evidence.updated", old["id"], _event_payload(updated, patch.get("change_reason", "新增出现渠道或议题关联")))
            return {**_present(updated), "deduplicated": True}
        created = store.create("evidence", item)
        _bind_aliases(store, created)
        store.publish("evidence.created", created["id"], _event_payload(created))
        return _present(created)


def _prepare_claim(store, data, old=None):
    item = {"subject": "", "statement": "", "evidence_version_ids": [], "attribution": "", "dispute_status": "unverified", "topic_id": None, "notes": "", "change_reason": "初次登记", "is_fixture": False, **(old or {}), **data}
    for key in ("subject", "statement", "attribution"):
        item[key] = text(item[key], key, key != "attribution")
    item["evidence_version_ids"] = references(store, item["evidence_version_ids"])
    if not item["evidence_version_ids"]:
        fail("说法须保留原材料版本引用")
    item["dispute_status"] = choice(item["dispute_status"], {"unverified", "reviewed", "disputed", "needs_review"}, "dispute_status")
    item["topic_id"] = topic(store, item["topic_id"])
    return {k: v for k, v in item.items() if k in CLAIM_FIELDS}


def _prepare_event(store, data, old=None):
    item = {"title": "", "event_type": "reported", "actors": [], "occurred_at": None, "time_precision": "unknown", "location": {"name": "未知", "country_code": None, "precision": "unknown"}, "claim_ids": [], "evidence_version_ids": [], "verification_status": "unverified", "topic_id": None, "notes": "", "change_reason": "初次登记", "is_fixture": False, **(old or {}), **data}
    item["title"] = text(item["title"], "title", True)
    item["actors"] = strings(item["actors"], "actors")
    precision = choice(item["time_precision"], {"unknown", "month", "day", "instant"}, "time_precision")
    if precision == "unknown" and item["occurred_at"]:
        fail("已知发生时间须明确对应精度")
    if precision != "unknown" and not item["occurred_at"]:
        fail("发生时间未知时须使用 unknown 精度")
    item["occurred_at"] = temporal(item["occurred_at"], "occurred_at", precision)
    location = item["location"]
    if not isinstance(location, dict):
        fail("location 须为对象")
    location = {"name": "未知", "country_code": None, "precision": "unknown", **location}
    choice(location["precision"], {"unknown", "country", "region", "city", "coordinate"}, "location.precision")
    if location["precision"] == "coordinate":
        for key, boundary in (("lat", 90), ("lon", 180)):
            val = location.get(key)
            if type(val) not in (int, float) or not math.isfinite(val) or abs(val) > boundary:
                fail(f"location.{key} 须为合法坐标")
    elif location.get("lat") is not None or location.get("lon") is not None:
        fail("非坐标精度的地点不得附加看似精确的事件坐标")
    item["location"] = location
    item["claim_ids"] = strings(item["claim_ids"], "claim_ids")
    for claim_id in item["claim_ids"]:
        store.get("claim", claim_id)
    item["evidence_version_ids"] = references(store, item["evidence_version_ids"])
    item["verification_status"] = choice(item["verification_status"], {"unverified", "reviewed", "disputed", "needs_review"}, "verification_status")
    item["topic_id"] = topic(store, item["topic_id"])
    return {k: v for k, v in item.items() if k in EVENT_FIELDS}


def _prepare_metric(store, data, old=None):
    item = {"indicator": "", "country_code": None, "value": None, "unit": "", "period": None, "published_at": None, "frequency": "unknown", "source_id": "manual", "evidence_version_ids": [], "topic_id": None, "notes": "", "change_reason": "初次登记", "is_fixture": False, **(old or {}), **data}
    item["indicator"] = text(item["indicator"], "indicator", True)
    item["unit"] = text(item["unit"], "unit", True)
    if item["value"] is not None and (type(item["value"]) not in (int, float) or not math.isfinite(item["value"])):
        fail("指标值须为有限数字或 null；未知不能以零替代")
    item["period"] = text(item["period"], "period", True)
    item["published_at"] = temporal(item["published_at"], "published_at")
    item["evidence_version_ids"] = references(store, item["evidence_version_ids"])
    item["topic_id"] = topic(store, item["topic_id"])
    return {k: v for k, v in item.items() if k in METRIC_FIELDS}



def upsert_observation(store, data):
    """Collector boundary: one observation per source, indicator, country and period."""
    with store.transaction():
        item = _prepare_metric(store, fields(data, METRIC_FIELDS))
        candidates = store.find("observation", "indicator", item["indicator"])
        old = next((row for row in candidates if all(row.get(key) == item.get(key) for key in ("source_id", "country_code", "period"))), None)
        if old:
            # Additional topic association does not replace the original metric's identity.
            meaningful = ("value", "unit", "published_at", "frequency", "evidence_version_ids")
            if all(old.get(key) == item.get(key) for key in meaningful):
                return old
            item["change_reason"] = data.get("change_reason") or "指标修订，观测期保持不变"
            revised = store.update("observation", old["id"], item, old["version"])
            store.publish("observation.updated", revised["id"], _event_payload(revised, item["change_reason"]))
            return revised
        record = store.create("observation", item)
        store.publish("observation.created", record["id"], _event_payload(record))
        return record

def _mark_dependents(store, evidence, reason):
    refs = {f'{evidence["id"]}@{v["version"]}' for v in store.history("evidence", evidence["id"])}
    for kind, status_field in (("claim", "dispute_status"), ("event", "verification_status")):
        for record in store.all(kind):
            dependent = bool(refs.intersection(record.get("evidence_version_ids", [])))
            if kind == "event" and not dependent:
                dependent = any(refs.intersection(store.get("claim", cid).get("evidence_version_ids", [])) for cid in record.get("claim_ids", []))
            if dependent:
                store.update(kind, record["id"], {status_field: "needs_review", "review_reason": reason}, record["version"])


def correct(store, evidence_id, body):
    allowed = {"reason", "status", "substantive", "title", "excerpt", "rights", "human_confirmed"}
    clean = fields(body, allowed)
    reason = text(clean.get("reason"), "reason", True)
    substantive = clean.get("substantive", False)
    if type(substantive) is not bool:
        fail("substantive 须为布尔值")
    status = choice(clean.get("status", "corrected"), EVIDENCE_STATUSES, "status")
    if status in {"corrected", "withdrawn"} and not substantive:
        fail("实质更正或撤回须由用户确认 substantive=true；格式变化不改变事实状态")
    with store.transaction():
        old = store.get("evidence", evidence_id)
        version = expected(body)
        patch = {k: clean[k] for k in ("title", "excerpt", "rights") if k in clean}
        patch.update({"status": status, "change_reason": reason})
        item = _prepare_evidence(store, patch, old)
        item["change_candidate"] = False if substantive else old.get("change_candidate", False)
        item["substantive_confirmed_at"] = store.now() if substantive else None
        updated = store.update("evidence", evidence_id, item, version)
        old_refs = [f'{evidence_id}@{v["version"]}' for v in store.history("evidence", evidence_id) if v["version"] < updated["version"]]
        dependency_change = substantive or status in {"inaccessible", "restricted"}
        if dependency_change:
            _mark_dependents(store, updated, reason)
        store.publish("evidence.corrected" if substantive else "evidence.updated", evidence_id, _event_payload(updated, reason, old_version_ids=old_refs, substantive=substantive, dependency_review=dependency_change))
        return _present(updated)


def split(store, evidence_id, body):
    clean = fields(body, {"channels", "reason"})
    reason = text(clean.get("reason"), "reason", True)
    selected = _channels(clean.get("channels", []))
    if not selected:
        fail("请选择要拆分的渠道")
    with store.transaction():
        old = store.get("evidence", evidence_id)
        version = expected(body)
        existing = {_channel_key(c): c for c in old.get("channels", [])}
        selected_keys = {_channel_key(c) for c in selected}
        if not selected_keys.issubset(existing) or len(selected_keys) >= len(existing):
            fail("拆分必须选择原记录的部分渠道，并至少保留一个渠道")
        selected = [existing[k] for k in existing if k in selected_keys]
        remaining = [v for k, v in existing.items() if k not in selected_keys]
        base = {k: copy.deepcopy(v) for k, v in old.items() if k in EVIDENCE_FIELDS}
        base.update({"channels": selected, "url": selected[0].get("url"), "source_id": selected[0].get("source_id"), "source_record_id": selected[0].get("source_record_id"), "change_reason": reason, "status": "unverified"})
        new = store.create("evidence", {**_prepare_evidence(store, base), "split_from": old["id"], "split_reason": reason})
        revised = store.update("evidence", old["id"], {"channels": remaining, "url": remaining[0].get("url"), "source_id": remaining[0].get("source_id"), "source_record_id": remaining[0].get("source_record_id"), "change_reason": reason, "split_children": old.get("split_children", []) + [new["id"]]}, version)
        _bind_aliases(store, revised)
        _bind_aliases(store, new)
        _mark_dependents(store, revised, reason)
        store.publish("evidence.corrected", old["id"], _event_payload(revised, reason, old_version_ids=[f'{old["id"]}@{v["version"]}' for v in store.history("evidence", old["id"])], substantive=True, split_evidence_id=new["id"]))
        store.publish("evidence.created", new["id"], _event_payload(new, reason))
        return {"original": _present(revised), "split": _present(new)}


def source_counts(records, store=None):
    chains, known_roots = set(), set()
    roots_by_record = {}
    for item in records:
        origin = item.get("origin_evidence_id")
        if not origin:
            continue
        seen = {item["id"]}
        while store and origin not in seen:
            seen.add(origin)
            ancestor = store.get("evidence", origin)
            if not ancestor.get("origin_evidence_id"):
                break
            origin = ancestor["origin_evidence_id"]
        chains.add(origin)
        known_roots.add(origin)
        roots_by_record[item["id"]] = origin
    reports = sum(max(1, len(item.get("channels", []))) for item in records)
    unknown = sum(1 for item in records if item["id"] not in roots_by_record and item["id"] not in known_roots)
    return {"report_count": reports, "identified_source_chain_count": len(chains), "independence_unconfirmed_count": unknown, "note": "来源链数量不等于事实证实次数"}


def _relations(store, evidence_id):
    result = {}
    for kind in ("claim", "event", "judgment", "scenario", "impact_path"):
        values = []
        for row in store.all(kind):
            refs = row.get("evidence_version_ids", []) + row.get("opposing_evidence_version_ids", [])
            for edge in row.get("edges", []):
                refs += edge.get("evidence_version_ids", [])
            if any(ref.rsplit("@", 1)[0] == evidence_id for ref in refs):
                values.append({"id": row["id"], "version": row["version"], "title": row.get("title") or row.get("statement") or row.get("conclusion"), "evidence_version_ids": refs})
        result[kind] = values
    return result


def _list(store, kind, query):
    limit, offset = page(query)
    simple = not any(query.get(key) for key in ("status", "material_type", "verification_status", "since", "until", "country_code", "similar_to"))
    if simple:
        result = store.list(kind, topic_id=query.get("topic_id"), limit=limit, offset=offset, search=query.get("search"))
        result["items"] = [_present(row) for row in result["items"]]
        if kind == "evidence":
            result["source_counts"] = source_counts(result["items"], store)
        return result
    rows = store.all(kind, topic_id=query.get("topic_id"))
    if query.get("search"):
        needle = query["search"].lower()
        rows = [r for r in rows if needle in json.dumps(r, ensure_ascii=False).lower()]
    for key in ("status", "material_type", "verification_status", "country_code"):
        if query.get(key):
            rows = [r for r in rows if (r.get("location", {}).get(key) if key == "country_code" and kind == "event" else r.get(key)) == query[key]]
    time_field = query.get("time_field", "occurred_at" if kind == "event" else "published_at")
    if time_field not in {"occurred_at", "published_at", "collected_at", "discovered_at", "updated_at"}:
        fail("不支持的时间筛选字段")
    for key, op in (("since", lambda v, b: v >= b), ("until", lambda v, b: v <= b)):
        if query.get(key):
            rows = [r for r in rows if r.get(time_field) and op(r[time_field], query[key])]
    if query.get("similar_to"):
        original = store.get("evidence", query["similar_to"])
        from difflib import SequenceMatcher
        rows = [{**r, "association_status": "candidate_only"} for r in rows if r["id"] != original["id"] and SequenceMatcher(None, r.get("title", ""), original["title"]).ratio() >= .65]
    result = {"items": [_present(r) for r in rows[offset:offset + limit]], "total": len(rows), "offset": offset, "limit": limit, "data_status": "fresh", "empty_reason": None if rows else "no_matches"}
    if kind == "evidence":
        result["source_counts"] = source_counts(rows, store)
    return result


def handle(store, method, segments, body, query):
    if not segments or segments[0] not in COLLECTIONS:
        return None
    kind = COLLECTIONS[segments[0]]
    if len(segments) == 1:
        if method == "GET":
            return _list(store, kind, query)
        if method == "POST":
            if kind == "evidence":
                return ingest(store, body)
            allowed, prepare = {"claim": (CLAIM_FIELDS, _prepare_claim), "event": (EVENT_FIELDS, _prepare_event), "observation": (METRIC_FIELDS, _prepare_metric)}[kind]
            with store.transaction():
                record = store.create(kind, prepare(store, fields(body, allowed)))
                store.publish(f"{kind}.created", record["id"], _event_payload(record))
                return record
    if len(segments) >= 2:
        record_id = segments[1]
        if len(segments) == 3:
            if segments[2] == "history" and method == "GET":
                latest = store.get(kind, record_id)
                values = []
                for v in store.history(kind, record_id):
                    shown = _present(v)
                    if kind == "evidence" and (not _excerpt_allowed(latest.get("rights", {}), "display") or latest.get("status") == "restricted"):
                        shown.update({"excerpt": "", "translation": "", "content_restricted": True})
                    values.append(shown)
                return {"items": values}
            if kind == "evidence" and method == "POST":
                if segments[2] == "corrections":
                    return correct(store, record_id, body)
                if segments[2] == "split":
                    return split(store, record_id, body)
        if len(segments) == 2:
            if method == "GET":
                record = _present(store.get(kind, record_id))
                if kind == "evidence":
                    record["relations"] = _relations(store, record_id)
                    record["source_counts"] = source_counts([record], store)
                return record
            if method == "PATCH":
                with store.transaction():
                    old = store.get(kind, record_id)
                    allowed, prepare = {"evidence": (EVIDENCE_FIELDS, _prepare_evidence), "claim": (CLAIM_FIELDS, _prepare_claim), "event": (EVENT_FIELDS, _prepare_event), "observation": (METRIC_FIELDS, _prepare_metric)}[kind]
                    clean = fields(body, allowed)
                    if kind == "evidence" and clean.get("status") in {"corrected", "withdrawn", "inaccessible", "restricted"} and clean.get("status") != old.get("status"):
                        fail("更正、撤回或访问限制请使用 corrections 接口，以传播依赖状态")
                    if kind == "evidence" and "topic_ids" in clean and "topic_id" not in clean and old.get("topic_id") not in clean["topic_ids"]:
                        clean["topic_id"] = clean["topic_ids"][0] if clean["topic_ids"] else None
                    item = prepare(store, clean, old)
                    if kind == "evidence" and any(item.get(k) != old.get(k) for k in ("title", "excerpt")):
                        item["change_candidate"] = True
                    updated = store.update(kind, record_id, item, expected(body))
                    store.publish(f"{kind}.updated", record_id, _event_payload(updated, clean.get("change_reason")))
                    return _present(updated)
    raise ApiError(405, "method_not_allowed", "此资源不支持该操作；历史记录不能直接删除")
