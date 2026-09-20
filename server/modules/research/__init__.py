"""M4: user-owned topics, versioned reasoning, scenarios, paths and reviews."""
import copy
import json
from server.platform.errors import ApiError
from server.platform.time_utils import in_range
from server.modules.knowledge.validation import choice, expected, fail, fields, page, references, strings, temporal, text, topic
from server.modules.knowledge import _present as present_evidence, source_counts

COLLECTIONS = {"topics": "topic", "judgments": "judgment", "scenarios": "scenario", "impact-paths": "impact_path", "reviews": "review"}
TOPIC_FIELDS = {"question", "regions", "actors", "time_range", "keywords", "exclude_keywords", "rationale", "status", "followed", "reading_baseline", "coverage_gaps", "source_ids", "pinned", "is_fixture"}
JUDGMENT_FIELDS = {"topic_id", "conclusion", "judgment_type", "evidence_version_ids", "opposing_evidence_version_ids", "assumptions", "missing_evidence", "confidence", "confidence_reason", "valid_until", "outcome_criteria", "review_date", "status", "author", "reviewer", "change_reason", "is_fixture"}
SCENARIO_FIELDS = {"topic_id", "title", "description", "valid_until", "assumptions", "evidence_version_ids", "opposing_evidence_version_ids", "counterevidence_search", "signals", "invalidation_conditions", "review_date", "status", "change_reason", "author", "reviewer", "is_fixture"}
PATH_FIELDS = {"topic_id", "title", "nodes", "edges", "status", "change_reason", "author", "reviewer", "is_fixture"}
REVIEW_FIELDS = {"topic_id", "judgment_id", "judgment_version", "outcome", "rationale", "evidence_version_ids", "author", "change_reason", "is_fixture", "next_review_date"}
STATUSES = {"draft", "reviewed", "needs_review", "withdrawn"}


def _topic(store, data, old=None):
    item = {"question": "", "regions": [], "actors": [], "time_range": "", "keywords": [], "exclude_keywords": [], "rationale": "", "status": "active", "followed": True, "reading_baseline": store.now(), "coverage_gaps": [], "source_ids": [], "pinned": False, "is_fixture": False, **(old or {}), **data}
    item["question"] = text(item["question"], "question", True)
    for key in ("regions", "actors", "keywords", "exclude_keywords", "coverage_gaps", "source_ids"):
        item[key] = strings(item[key], key)
    for key in ("followed", "pinned"):
        if type(item[key]) is not bool:
            fail(f"{key} 须为布尔值")
    if not isinstance(item["time_range"], (str, dict)):
        fail("time_range 须为时间范围文本或对象")
    item["status"] = choice(item["status"], {"active", "paused", "archived"}, "status")
    item["rationale"] = text(item["rationale"], "rationale")
    item["reading_baseline"] = temporal(item["reading_baseline"], "reading_baseline")
    if old and item["reading_baseline"] != old.get("reading_baseline"):
        fail("初始阅读基线不能通过议题编辑改变；请显式标记展示变化已读")
    return {k: v for k, v in item.items() if k in TOPIC_FIELDS}


def _reason(item, old):
    if old:
        text(item.get("change_reason"), "change_reason", True)


def _research_base(store, item, old):
    item["topic_id"] = topic(store, item.get("topic_id"))
    if not item["topic_id"]:
        fail("研究记录须关联议题")
    item["status"] = choice(item.get("status", "draft"), STATUSES, "status")
    for key in ("evidence_version_ids", "opposing_evidence_version_ids"):
        item[key] = references(store, item.get(key, []), key, allow_deleted=(old or {}).get(key, []))
    item["assumptions"] = strings(item.get("assumptions", []), "assumptions")
    item["valid_until"] = temporal(item.get("valid_until"), "valid_until")
    item["review_date"] = temporal(item.get("review_date"), "review_date")
    _reason(item, old)
    return item


def _judgment(store, data, old=None):
    item = {"topic_id": None, "conclusion": "", "judgment_type": "explanation", "evidence_version_ids": [], "opposing_evidence_version_ids": [], "assumptions": [], "missing_evidence": "", "confidence": "low", "confidence_reason": "", "valid_until": None, "outcome_criteria": "", "review_date": None, "status": "draft", "author": "本地用户", "reviewer": None, "change_reason": "初次判断", "is_fixture": False, **(old or {}), **data}
    _research_base(store, item, old)
    item["conclusion"] = text(item["conclusion"], "conclusion", True)
    item["judgment_type"] = choice(item["judgment_type"], {"explanation", "prediction"}, "judgment_type")
    item["confidence"] = choice(item["confidence"], {"low", "medium", "high"}, "confidence")
    for key in ("author", "confidence_reason", "missing_evidence", "outcome_criteria"):
        item[key] = text(item[key], key, key == "author")
    if item["judgment_type"] == "prediction" and (not item["valid_until"] or not item["outcome_criteria"]):
        fail("可判定预测必须有适用期限 valid_until 和结果条件 outcome_criteria")
    item["evidence_support"] = "evidence_linked" if item["evidence_version_ids"] else "assumption_only"
    item["support_label"] = "已登记证据引用，仍需核查" if item["evidence_version_ids"] else "假设型暂定判断／缺乏证据支持"
    if not item["evidence_version_ids"] and not item["missing_evidence"]:
        item["missing_evidence"] = "尚未登记支持证据"
    if item["status"] == "reviewed":
        text(item["reviewer"], "reviewer", True)
        text(item["confidence_reason"], "confidence_reason", True)
        if not item["evidence_version_ids"] and not item["assumptions"]:
            fail("无支持证据的已审阅判断必须说明具体假设")
        if not item["review_date"]:
            fail("已审阅判断须设置下次复查日期")
    keys = JUDGMENT_FIELDS | {"evidence_support", "support_label"}
    return {k: v for k, v in item.items() if k in keys}


def _scenario(store, data, old=None):
    item = {"topic_id": None, "title": "", "description": "", "valid_until": None, "assumptions": [], "evidence_version_ids": [], "opposing_evidence_version_ids": [], "counterevidence_search": "", "signals": [], "invalidation_conditions": "", "review_date": None, "status": "draft", "change_reason": "初次情景", "author": "本地用户", "reviewer": None, "is_fixture": False, **(old or {}), **data}
    _research_base(store, item, old)
    item["title"] = text(item["title"], "title", True)
    item["description"] = text(item["description"], "description", True)
    item["signals"] = strings(item["signals"], "signals")
    item["counterevidence_search"] = text(item["counterevidence_search"], "counterevidence_search")
    item["invalidation_conditions"] = text(item["invalidation_conditions"], "invalidation_conditions")
    item["evidence_support"] = "evidence_linked" if item["evidence_version_ids"] else "assumption_only"
    item["support_label"] = "已登记证据引用，仍需核查" if item["evidence_version_ids"] else "假设情景／缺乏证据支持"
    if item["status"] == "reviewed":
        if not item["valid_until"] or not item["review_date"] or not item["assumptions"] or not item["signals"] or not item["invalidation_conditions"]:
            fail("已审阅情景须包含期限、假设、观察信号、失效条件和复查日期")
        if not item["opposing_evidence_version_ids"] and not item["counterevidence_search"]:
            fail("未找到反证时须如实填写 counterevidence_search 检索说明")
        text(item["reviewer"], "reviewer", True)
    return {k: v for k, v in item.items() if k in SCENARIO_FIELDS | {"evidence_support", "support_label"}}


def _path(store, data, old=None):
    item = {"topic_id": None, "title": "", "nodes": [], "edges": [], "status": "draft", "change_reason": "初次影响路径", "author": "本地用户", "reviewer": None, "is_fixture": False, **(old or {}), **data}
    item["topic_id"] = topic(store, item["topic_id"])
    if not item["topic_id"]:
        fail("影响路径须关联议题")
    item["title"] = text(item["title"], "title", True)
    item["status"] = choice(item["status"], STATUSES, "status")
    _reason(item, old)
    if not isinstance(item["nodes"], list) or not isinstance(item["edges"], list):
        fail("nodes 和 edges 须为列表")
    nodes, ids = [], set()
    for node in item["nodes"]:
        if not isinstance(node, dict):
            fail("每个路径节点须为 {id,label} 对象")
        node_id = text(node.get("id"), "node.id", True)
        if node_id in ids:
            fail("路径节点 id 不可重复")
        ids.add(node_id)
        nodes.append({"id": node_id, "label": text(node.get("label"), "node.label", True), "note": text(node.get("note", ""), "node.note")})
    edges = []
    for edge in item["edges"]:
        if not isinstance(edge, dict) or edge.get("from") not in ids or edge.get("to") not in ids or edge["from"] == edge["to"]:
            fail("路径关系的 from/to 须指向两个不同的已登记节点")
        status = choice(edge.get("status", "unverified"), {"observed", "assumption", "unverified"}, "edge.status")
        refs = references(store, edge.get("evidence_version_ids", []), allow_deleted=[ref for prior in (old or {}).get("edges", []) for ref in prior.get("evidence_version_ids", [])])
        if status in {"observed", "assumption"} and not refs:
            fail("已观察关联和有依据的分析假设须引用证据；缺证据请标待验证")
        edges.append({"from": edge["from"], "to": edge["to"], "status": status, "evidence_version_ids": refs, "note": text(edge.get("note", ""), "edge.note"), "needs_review": bool(edge.get("needs_review", False))})
    item["nodes"], item["edges"] = nodes, edges
    if item["status"] == "reviewed" and (len(nodes) < 2 or not edges):
        fail("已审阅路径须至少有两个节点和一段关系")
    return {k: v for k, v in item.items() if k in PATH_FIELDS}


def _review(store, data, old=None):
    item = {"topic_id": None, "judgment_id": None, "judgment_version": None, "outcome": "indeterminate", "rationale": "", "evidence_version_ids": [], "author": "本地用户", "change_reason": "首次复盘", "is_fixture": False, **(old or {}), **data}
    judgment = store.get("judgment", text(item["judgment_id"], "judgment_id", True))
    item["judgment_version"] = item["judgment_version"] or judgment["version"]
    if type(item["judgment_version"]) is not int or not any(v["version"] == item["judgment_version"] for v in store.history("judgment", judgment["id"])):
        fail("复盘须引用实际存在的判断版本")
    if item["topic_id"] and item["topic_id"] != judgment["topic_id"]:
        fail("复盘议题须与判断所属议题一致")
    item["topic_id"] = judgment["topic_id"]
    item["outcome"] = choice(item["outcome"], {"meets", "does_not_meet", "partly_meets", "indeterminate"}, "outcome")
    item["rationale"] = text(item["rationale"], "rationale", True)
    item["author"] = text(item["author"], "author", True)
    item["next_review_date"] = temporal(item.get("next_review_date"), "next_review_date")
    item["evidence_version_ids"] = references(store, item["evidence_version_ids"], allow_deleted=(old or {}).get("evidence_version_ids", []))
    _reason(item, old)
    return {k: v for k, v in item.items() if k in REVIEW_FIELDS}


PREPARERS = {"topic": (TOPIC_FIELDS, _topic), "judgment": (JUDGMENT_FIELDS, _judgment), "scenario": (SCENARIO_FIELDS, _scenario), "impact_path": (PATH_FIELDS, _path), "review": (REVIEW_FIELDS, _review)}


def _payload(record, kind):
    return {"topic_id": record["id"] if kind == "topic" else record.get("topic_id"), "title": record.get("question") or record.get("title") or record.get("conclusion") or record.get("rationale"), "version": record["version"], "object_kind": kind, "evidence_version_ids": record.get("evidence_version_ids", []), "reason": record.get("change_reason"), "support_label": record.get("support_label"), "evidence_support": record.get("evidence_support"), "needs_review": record.get("status") == "needs_review"}


def _review_summary(items):
    counts = {key: 0 for key in ("meets", "does_not_meet", "partly_meets", "indeterminate")}
    for row in items:
        counts[row["outcome"]] += 1
    return {"counts": counts, "decidable_count": len(items) - counts["indeterminate"], "indeterminate_count": counts["indeterminate"], "note": "无法判定单列，不视为失败；本版不发布预测准确率"}


def _list(store, kind, query):
    limit, offset = page(query)
    if not any(query.get(k) for k in ("status", "due_before", "since", "until", "judgment_type", "outcome", "changed")):
        result = store.list(kind, topic_id=query.get("topic_id"), limit=limit, offset=offset, search=query.get("search"))
        if kind == "review":
            result["summary"] = _review_summary(store.all("review", topic_id=query.get("topic_id")))
        return result
    rows = store.all(kind, topic_id=query.get("topic_id"))
    for key in ("status", "judgment_type", "outcome"):
        if query.get(key):
            rows = [r for r in rows if r.get(key) == query[key]]
    if query.get("due_before"):
        rows = [r for r in rows if in_range(r.get("review_date"),until=query["due_before"]) and r.get("status") != "withdrawn"]
    if query.get("search"):
        rows = [r for r in rows if query["search"].lower() in json.dumps(r, ensure_ascii=False).lower()]
    if query.get("changed") == "true":
        rows = [r for r in rows if r["version"] > 1]
    if query.get("since") or query.get("until"):
        rows = [r for r in rows if in_range(r.get("updated_at"),query.get("since"),query.get("until"))]
    result = {"items": rows[offset:offset + limit], "total": len(rows), "limit": limit, "offset": offset, "data_status": "fresh", "empty_reason": None if rows else "no_matches"}
    if kind == "review":
        result["summary"] = _review_summary(rows)
    return result


def _all_refs(value):
    refs = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"evidence_version_ids", "opposing_evidence_version_ids"} and isinstance(child, list):
                refs.update(child)
            else:
                refs.update(_all_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_all_refs(child))
    return refs


def _evidence_view(store, record, action):
    # Later access restrictions also apply when reading earlier versions.
    latest = store.get("evidence", record["id"])
    result = present_evidence(record, action)
    permission = latest.get("rights", {}).get(action)
    if permission not in (True, "excerpt", "full", "allowed") or latest.get("rights",{}).get("store") not in (True,"excerpt","full","allowed") or latest.get("status") == "restricted":
        result["excerpt"], result["translation"] = "", ""
        result["content_restricted"] = True
    return result


def bundle(store, topic_id, include_history=False, action="display"):
    result = {"topic": store.get("topic", topic_id)}
    for key, kind in (("evidence", "evidence"), ("claims", "claim"), ("events", "event"), ("judgments", "judgment"), ("scenarios", "scenario"), ("impact_paths", "impact_path"), ("reviews", "review"), ("observations", "observation")):
        result[key] = store.all(kind, topic_id=topic_id)
    # Include material referenced from another topic or subsequently unlinked.
    refs = _all_refs(result)
    evidence_ids = {r["id"] for r in result["evidence"]}
    for ref in refs:
        evidence_id = ref.rsplit("@", 1)[0]
        if evidence_id not in evidence_ids:
            result["evidence"].append(store.get("evidence", evidence_id))
            evidence_ids.add(evidence_id)
    if include_history:
        history = {"topic": {topic_id: store.history("topic", topic_id)}}
        for key, kind in (("evidence", "evidence"), ("claims", "claim"), ("events", "event"), ("judgments", "judgment"), ("scenarios", "scenario"), ("impact_paths", "impact_path"), ("reviews", "review"), ("observations", "observation")):
            history[key] = {r["id"]: store.history(kind, r["id"]) for r in result[key]}
        refs.update(_all_refs(history))
        history["evidence"] = {eid: [_evidence_view(store, v, action) for v in versions] for eid, versions in history["evidence"].items()}
        result["histories"] = history
    result["citations"] = [_evidence_view(store, store.version(ref), action) for ref in sorted(refs)]
    result["evidence"] = [_evidence_view(store, row, action) for row in result["evidence"]]
    result["source_counts"] = source_counts(result["evidence"], store)
    source_ids = {r.get("source_id") for r in result["evidence"] + result["observations"]}
    public_source_fields = {"id", "version", "name", "adapter", "domain", "languages", "regions", "license_url", "checked_at", "rights", "status", "last_success", "data_as_of"}
    result["sources"] = [{k: v for k, v in row.items() if k in public_source_fields} for row in store.all("source") if row["id"] in source_ids]
    result["review_summary"] = _review_summary(result["reviews"])
    result["unknowns"] = {"coverage_gaps": result["topic"].get("coverage_gaps", []), "missing_evidence": [{"judgment_id": row["id"], "description": row.get("missing_evidence"), "support_label": row.get("support_label")} for row in result["judgments"] if row.get("missing_evidence") or row.get("evidence_support") == "assumption_only"], "event_time_unknown": [row["id"] for row in result["events"] if row.get("time_precision") == "unknown"], "event_location_unknown": [row["id"] for row in result["events"] if row.get("location", {}).get("precision") == "unknown"]}
    return result


def export(store, query):
    topic_id = query.get("topic_id")
    if not topic_id:
        fail("导出须指定 topic_id")
    fmt = choice(query.get("format", "json"), {"json", "markdown"}, "format")
    data = bundle(store, topic_id, include_history=True, action="export")
    data["generated_at"] = store.now()
    data["schema_version"] = 1
    data["boundaries"] = ["已审阅表示用户审阅，不表示客观真相已获证明", "假设型暂定判断始终缺乏证据支持", "导出仅包含允许导出的材料内容，不包含密钥"]
    if fmt == "json":
        return data
    lines = [f'# {data["topic"]["question"]}', "", f'生成时间：{data["generated_at"]}', "", "已审阅表示用户审阅，不表示客观真相已获证明。", ""]
    labels = (("judgments", "研究判断", "conclusion"), ("scenarios", "发展情景", "title"), ("impact_paths", "影响路径", "title"), ("events", "事件", "title"), ("claims", "主体说法", "statement"), ("observations", "国家指标", "indicator"), ("reviews", "复盘", "rationale"))
    for key, label, title_key in labels:
        lines.extend([f"## {label}", ""])
        if not data[key]:
            lines.extend(["尚未登记。", ""])
        for row in data[key]:
            lines.extend([f'### {row.get(title_key, row["id"])}', "", f'记录：{row["id"]} · 版本 {row["version"]}', "", f'状态：{row.get("status", row.get("verification_status", row.get("outcome", "待核查")))}', ""])
            if row.get("support_label"):
                lines.extend([row["support_label"], ""])
            lines.extend(["```json", json.dumps(row, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## 引用的材料版本", ""])
    for row in data["citations"]:
        lines.extend([f'### {row.get("title", "未知标题")}', "", f'版本：{row["id"]}@{row["version"]}', f'原始链接：{row.get("url") or "未登记"}', f'发布者：{row.get("publisher") or "未知"}', f'发布时间：{row.get("published_at") or "未知"}', f'采集时间：{row.get("collected_at") or "未知"}', f'摘录：{row.get("excerpt") or ("授权限制，不导出内容" if row.get("content_restricted") else "未登记")}', ""])
    lines.extend(["## 未知项和完整版本记录", "", "```json", json.dumps({"unknowns": data["unknowns"], "histories": data["histories"], "sources": data["sources"], "boundaries": data["boundaries"]}, ensure_ascii=False, indent=2), "```", ""])
    return {"filename": f"world-insight-{topic_id}.md", "format": "markdown", "content": "\n".join(lines), "generated_at": data["generated_at"]}


def on_event(store, event):
    """Idempotent owner-side correction propagation; root delivery wraps one transaction."""
    payload = event.get("payload", {})
    if event.get("type") not in {"evidence.corrected", "evidence.updated"}:
        return
    if event["type"] == "evidence.updated" and not payload.get("dependency_review"):
        return
    evidence_id = payload.get("evidence_id") or event["aggregate_id"]
    refs = set(payload.get("old_version_ids", []))
    if not refs:
        refs = {f'{evidence_id}@{row["version"]}' for row in store.history("evidence", evidence_id)}
    with store.transaction():
        for kind in ("judgment", "scenario", "impact_path"):
            for row in store.all(kind):
                if event["id"] in row.get("review_event_ids", []):
                    continue
                affected = refs.intersection(_all_refs(row))
                if not affected:
                    continue
                reason = payload.get("reason") or "所引用的材料已更正或失效，请重新审阅"
                patch = {"status": "withdrawn" if row.get("status") == "withdrawn" else "needs_review", "needs_review": True, "review_reason": reason, "review_event_ids": row.get("review_event_ids", []) + [event["id"]], "review_evidence_version_ids": sorted(affected)}
                if kind == "impact_path":
                    patch["edges"] = [{**edge, "needs_review": True, "review_reason": reason} if refs.intersection(edge.get("evidence_version_ids", [])) else edge for edge in row.get("edges", [])]
                revised = store.update(kind, row["id"], patch, row["version"])
                store.publish("research.needs_review", row["id"], {**_payload(revised, kind), "reason": reason, "source_event_id": event["id"], "evidence_id": evidence_id, "evidence_version_ids": sorted(affected)}, event_id=f'research-review:{event["id"]}:{kind}:{row["id"]}')


def lifecycle_change(store, kind, record_id, expected_version, deleted, reason):
    if kind not in COLLECTIONS.values():
        fail("不是研究模块拥有的记录")
    text(reason, "reason", True)
    with store.transaction():
        revised = store.update(kind, record_id, {"deleted": bool(deleted), "deleted_at": store.now() if deleted else None,
            "deleted_reason": reason, "restored_at": None if deleted else store.now()}, expected_version)
        store.publish("record.deleted" if deleted else "record.restored", record_id, {**_payload(revised, kind), "reason": reason})
        return revised


def handle(store, method, segments, body, query):
    if segments == ["exports"] and method == "GET":
        return export(store, query)
    if not segments or segments[0] not in COLLECTIONS:
        return None
    kind = COLLECTIONS[segments[0]]
    if len(segments) == 1:
        if method == "GET":
            return _list(store, kind, query)
        if method == "POST":
            allowed, prepare = PREPARERS[kind]
            with store.transaction():
                record = store.create(kind, prepare(store, fields(body, allowed)))
                store.publish(f"{kind}.created", record["id"], _payload(record, kind))
                if kind == "review":
                    judgment = store.get("judgment", record["judgment_id"])
                    if judgment["version"] == record["judgment_version"]:
                        revised = store.update("judgment", judgment["id"], {"last_reviewed_version": record["judgment_version"], "last_review_id": record["id"], "last_reviewed_at": record["created_at"], "review_date": record.get("next_review_date"), "change_reason": "完成该版本复盘：" + record["rationale"]}, judgment["version"])
                        store.publish("judgment.revised", revised["id"], _payload(revised, "judgment"))
                return record
    if len(segments) >= 2:
        record_id = segments[1]
        if len(segments) == 3 and method == "GET":
            if segments[2] == "history":
                return {"items": store.history(kind, record_id)}
            if kind == "topic" and segments[2] == "bundle":
                return bundle(store, record_id)
        if len(segments) == 2:
            if method == "GET":
                return store.get(kind, record_id)
            if method == "PATCH":
                allowed, prepare = PREPARERS[kind]
                clean = fields(body, allowed)
                if kind != "topic":
                    text(clean.get("change_reason"), "change_reason", True)
                with store.transaction():
                    old = store.get(kind, record_id)
                    if old.get("deleted"):
                        fail("记录已在回收站，请先恢复后编辑", "record_deleted")
                    prepared = prepare(store, clean, old)
                    if old.get("status") == "needs_review" and prepared.get("status") == "reviewed":
                        prepared.update({"review_reason": None, "review_evidence_version_ids": [], "review_resolved_at": store.now(), "review_resolution_reason": clean.get("change_reason")})
                    updated = store.update(kind, record_id, prepared, expected(body))
                    store.publish("judgment.revised" if kind == "judgment" else f"{kind}.updated", record_id, _payload(updated, kind))
                    return updated
    raise ApiError(405, "method_not_allowed", "此资源不支持该操作；归档或撤回保留历史")
