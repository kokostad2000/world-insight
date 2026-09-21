"""M3 receipt of successful collector ingestion, separate from evidence history.

Call inside the SAME transaction as successful ``knowledge.ingest``. A receipt
means this material was received by the local collector, not newly discovered,
factually changed, or saved with its body. It never renews content retention.
Only trusted collector context supplies the source/job/time; these are not
editable evidence fields. Failed fetches, 304 responses without ingestion, and
human edits must not call this boundary as a collector.
"""
from datetime import datetime, timezone

from server.platform.errors import ApiError

from .validation import fail, text


KIND = "evidence_acquisition"


def _optional_get(store, kind, record_id):
    try:
        return store.get(kind, record_id)
    except ApiError as error:
        if error.status == 404 and error.code == "not_found":
            return None
        raise


def _stamp(value, name):
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError()
        return instant.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (AttributeError, TypeError, ValueError, OverflowError):
        fail(f"{name} 须为含时区的实际收取时刻", "invalid_acquisition_time")


def record_acquisition(store, ingest_result, *, origin, source_id, job_id=None, collected_at=None):
    """Upsert the latest receipt; return None for manual/suppressed ingestion.

    The receipt ID equals evidence_id, allowing one indexed lookup per displayed
    material. Receipt versions preserve past accepted source/job references;
    an older completion cannot replace a more recent collection timestamp.
    A missing legacy Source or absent job stays explicitly unknown (None).
    A supplied job must exist and belong to the supplied source.

    This helper joins an outer transaction; the ingest owner MUST keep its
    successful material write and this call inside that transaction. Never call
    after a failed/suppressed ingestion or from source-wide success handling.
    ``collected_at`` is the collector's local successful receipt time, NOT the
    publisher's date, provider batch time, or Evidence's original collection.
    Cached metadata can be received locally again; this is no claim of a new
    upstream request or fresher upstream coverage.
    """
    if origin == "manual":
        return None
    if origin != "collector":
        fail("未知材料登记方式", "invalid_acquisition_origin")
    if not isinstance(ingest_result, dict):
        fail("采集凭据须来自成功的材料登记结果", "invalid_acquisition")
    if ingest_result.get("suppressed") or ingest_result.get("deleted"):
        return None
    evidence_id = text(ingest_result.get("id"), "evidence_id", True, 1000)
    version = ingest_result.get("version")
    if type(version) is not int or version < 1:
        fail("采集凭据须引用明确的材料版本", "invalid_acquisition")
    source_id = text(source_id, "source_id", True, 1000)
    if job_id is not None:
        job_id = text(job_id, "job_id", True, 1000)
    with store.transaction():
        evidence = store.get("evidence", evidence_id)
        if evidence.get("deleted"):
            return None
        if evidence["version"] != version:
            raise ApiError(409, "acquisition_version_conflict", "采集结果与当前材料版本不一致，须在登记事务内记录凭据")
        known_sources = {evidence.get("source_id")}
        known_sources.update(channel.get("source_id") for channel in evidence.get("channels", []) if isinstance(channel, dict))
        if source_id not in known_sources:
            fail("采集来源不在材料出处中", "acquisition_source_mismatch")
        source = _optional_get(store, "source", source_id)
        job = store.get("collection_job", job_id) if job_id is not None else None
        if job and job.get("source_id") != source_id:
            fail("采集任务与来源不一致", "acquisition_source_mismatch")
        received_at = _stamp(store.now(), "received_at")
        payload = {
            "evidence_id": evidence_id,
            "evidence_version_id": f"{evidence_id}@{version}",
            "source_id": source_id,
            "source_version": source["version"] if source else None,
            "job_id": job_id,
            "job_version": job["version"] if job else None,
            "collected_at": _stamp(collected_at if collected_at is not None else received_at, "collected_at"),
            "is_fixture": bool(evidence.get("is_fixture")),
        }
        old = latest_acquisition(store, evidence_id)
        if old and (old["collected_at"] > payload["collected_at"] or all(old.get(key) == value for key, value in payload.items())):
            return old
        payload["received_at"] = received_at
        if old:
            return store.update(KIND, evidence_id, payload, old["version"])
        return store.create(KIND, payload, record_id=evidence_id)


def latest_acquisition(store, evidence_id):
    """Read a material's latest receipt; missing legacy receipts stay unknown."""
    return _optional_get(store, KIND, evidence_id)


def acquisition_index(store):
    """Read current receipts once for collection-time filtering, never cache globally."""
    return {row["evidence_id"]: row for row in store.all(KIND)}
