"""Domain input checks shared by knowledge and research (no persistence)."""
import re
from datetime import date, datetime
from server.platform.errors import ApiError


def fail(message, code="validation_error", details=None):
    raise ApiError(400, code, message, details)


def text(value, name, required=False, max_length=100000):
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        fail(f"{name} 必须是非空文本" if required else f"{name} 必须是文本")
    if len(value) > max_length:
        fail(f"{name} 超出长度限制")
    return value.strip()


def strings(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        fail(f"{name} 必须是非空文本组成的列表")
    return list(dict.fromkeys(x.strip() for x in value))


def choice(value, choices, name):
    if value not in choices:
        fail(f"{name} 不属于允许的状态", details={"allowed": sorted(choices)})
    return value


def temporal(value, name, precision=None):
    if value is None or value == "":
        return None
    text(value, name, True)
    try:
        if precision == "month":
            if not re.fullmatch(r"\d{4}-\d{2}", value):
                raise ValueError()
            date.fromisoformat(value + "-01")
        elif precision == "day" or (precision is None and len(value) == 10):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError()
            date.fromisoformat(value)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
    except ValueError:
        fail(f"{name} 格式无效；日期保留原精度，时间须包含时区")
    return value


def references(store, value, name="evidence_version_ids", allow_deleted=()):
    refs = strings(value, name)
    for ref in refs:
        if not re.fullmatch(r"[^@]+@[1-9]\d*", ref):
            fail(f"{name} 必须引用明确材料版本，如 evidence_id@1")
        store.version(ref)
        if store.get("evidence", ref.rsplit("@", 1)[0]).get("deleted") and ref not in allow_deleted:
            fail("新引用不能使用回收站材料；原有引用仍保留占位", "deleted_reference")
    return refs


def expected(body):
    value = body.get("expected_version")
    if type(value) is not int or value < 1:
        fail("保存修改必须提交 expected_version", "expected_version_required")
    return value


def page(query):
    try:
        limit = min(200, max(1, int(query.get("limit", 100))))
        offset = max(0, int(query.get("offset", 0)))
    except (TypeError, ValueError):
        fail("分页参数须为整数")
    return limit, offset


def fields(body, allowed):
    if not isinstance(body, dict):
        fail("请求内容须为 JSON 对象")
    forbidden = set(body) - set(allowed) - {"expected_version"}
    if forbidden:
        fail("包含不允许编辑的字段", details={"fields": sorted(forbidden)})
    return {key: value for key, value in body.items() if key in allowed}


def topic(store, value):
    if value:
        store.get("topic", value)
    return value or None
