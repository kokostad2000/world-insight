#!/usr/bin/env python3
"""Capture one read-only, non-overwriting snapshot for the seven-day real trial."""

import argparse
import hashlib
import http.client
import json
import os
import sqlite3
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "world_insight_trial_snapshot/v2"
AUDIT_FIELDS = {
    "evidence": ("id", "version", "title", "source_id", "source_record_id", "url", "publisher",
                 "language", "author", "material_type", "published_at", "source_updated_at",
                 "collected_at", "discovered_at", "provider_seen_at", "status", "rights", "notes",
                 "change_reason", "origin_evidence_id", "topic_id", "topic_ids", "updated_at"),
    "claim": ("id", "version", "subject", "statement", "topic_id", "dispute_status", "evidence_version_ids",
              "attribution", "notes", "change_reason", "updated_at"),
    "event": ("id", "version", "title", "topic_id", "event_type", "occurred_at", "time_precision",
              "location", "actors", "claim_ids", "evidence_version_ids", "verification_status", "notes",
              "change_reason", "updated_at"),
    "judgment": ("id", "version", "conclusion", "topic_id", "judgment_type", "evidence_version_ids",
                 "opposing_evidence_version_ids", "assumptions", "missing_evidence", "confidence",
                 "confidence_reason", "valid_until", "outcome_criteria", "evidence_support", "support_label",
                 "review_date", "status", "author", "reviewer", "change_reason", "updated_at"),
    "scenario": ("id", "version", "title", "topic_id", "evidence_version_ids",
                 "opposing_evidence_version_ids", "review_date", "status", "reviewer", "updated_at"),
    "impact_path": ("id", "version", "title", "topic_id", "status", "reviewer", "updated_at"),
    "review": ("id", "version", "topic_id", "judgment_id", "judgment_version", "outcome",
               "evidence_version_ids", "author", "updated_at"),
    "observation": ("id", "version", "topic_id", "topic_ids", "indicator", "country_code", "period",
                    "published_at", "source_id", "evidence_version_ids", "updated_at"),
    "change": ("id", "version", "topic_id", "topic_ids", "type", "aggregate_id", "title", "detail",
               "reason", "object_kind", "object_version", "discovered_at", "occurred_at", "status",
               "needs_review", "missing_evidence", "evidence_support", "support_label",
               "evidence_version_ids", "updated_at"),
}


def fail(message):
    raise SystemExit(message)


def current_records(db, include_deleted=False):
    rows = db.execute("SELECT kind,data FROM records ORDER BY kind,id").fetchall()
    result = []
    for kind, raw in rows:
        record = json.loads(raw)
        if include_deleted or not record.get("deleted"):
            result.append((kind, record))
    return result


def belongs(record, topic_ids):
    return record.get("topic_id") in topic_ids or bool(set(record.get("topic_ids") or []) & topic_ids)


def relevant(kind, record, topic_ids, topics):
    if belongs(record, topic_ids):
        return True
    if kind != "observation":
        return False
    for topic in topics:
        if topic["id"] not in topic_ids:
            continue
        countries = set(topic.get("country_codes") or [])
        sources = set(topic.get("source_ids") or [])
        if record.get("country_code") in countries and (not sources or record.get("source_id") in sources):
            return True
    return False


def projection(kind, record):
    return {key: record.get(key) for key in AUDIT_FIELDS[kind]}


def timestamp(value, name):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        fail(f"{name} must be an ISO 8601 timestamp with timezone")
    if parsed.tzinfo is None:
        fail(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def process_alive(pid):
    if type(pid) is not int or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def local_health(runtime):
    port = runtime.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        fail("runtime port is invalid")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        raw = response.read(64 * 1024 + 1)
    except OSError as exc:
        fail(f"running trial health check failed: {exc}")
    finally:
        connection.close()
    if response.status != 200 or len(raw) > 64 * 1024:
        fail("running trial health endpoint returned an invalid response")
    try:
        health = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        fail(f"running trial health response is invalid JSON: {exc}")
    expected = {
        "instance_id": runtime.get("instance_id"),
        "data_dir": str(Path(runtime.get("data_dir", "")).resolve()),
        "pid": runtime.get("pid"),
    }
    actual = {
        "instance_id": health.get("instance_id"),
        "data_dir": str(Path(health.get("data_dir", "")).resolve()),
        "pid": health.get("pid"),
    }
    if health.get("status") != "ok" or actual != expected:
        fail("running trial health identity does not match runtime.json")
    return health


def git_commit(root):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def git_clean(root):
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        return None, None
    rows = [line for line in result.stdout.splitlines() if line]
    return not rows, len(rows)


def projected_history(db, kind, record_ids, fields, since):
    if not record_ids:
        return []
    placeholders = ",".join("?" for _ in record_ids)
    rows = db.execute(
        f"SELECT data FROM versions WHERE kind=? AND id IN ({placeholders}) ORDER BY id,version",
        (kind, *sorted(record_ids)),
    ).fetchall()
    records = [json.loads(raw) for (raw,) in rows]
    result = []
    for record_id in sorted(record_ids):
        versions = [record for record in records if record.get("id") == record_id]
        baseline = [record for record in versions if timestamp(record["updated_at"], "history updated_at") < since]
        if baseline:
            result.append({key: baseline[-1].get(key) for key in fields})
        result.extend({key: record.get(key) for key in fields}
                      for record in versions if timestamp(record["updated_at"], "history updated_at") >= since)
    return result


def historical_fixtures(db, pairs):
    fixtures = []
    grouped = {}
    for kind, record_id in pairs:
        grouped.setdefault(kind, set()).add(record_id)
    for kind, record_ids in grouped.items():
        placeholders = ",".join("?" for _ in record_ids)
        rows = db.execute(
            f"SELECT id,version,data FROM versions WHERE kind=? AND id IN ({placeholders})",
            (kind, *sorted(record_ids)),
        ).fetchall()
        for record_id, version, raw in rows:
            if json.loads(raw).get("is_fixture"):
                fixtures.append(f"{kind}:{record_id}@{version}")
    return sorted(fixtures)


def load_start_snapshot(path):
    if path is None or not path.is_file():
        fail("daily and end snapshots require an existing --start-snapshot")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        fail(f"start snapshot is invalid JSON: {exc}")
    if payload.get("schema") != SCHEMA or payload.get("phase") != "start":
        fail("--start-snapshot must be a start snapshot using the current schema")
    return payload, hashlib.sha256(raw).hexdigest()


def evidence_references(value):
    references = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"evidence_version_ids", "opposing_evidence_version_ids"} and isinstance(child, list):
                references.update(ref for ref in child if isinstance(ref, str))
            else:
                references.update(evidence_references(child))
    elif isinstance(value, list):
        for child in value:
            references.update(evidence_references(child))
    return references


def citation_versions(db, references):
    result = []
    for reference in sorted(references):
        try:
            record_id, version_text = reference.rsplit("@", 1)
            version = int(version_text)
        except (ValueError, AttributeError):
            fail(f"invalid evidence version reference: {reference}")
        row = db.execute(
            "SELECT data FROM versions WHERE kind='evidence' AND id=? AND version=?",
            (record_id, version),
        ).fetchone()
        if row is None:
            fail(f"missing evidence version reference: {reference}")
        record = json.loads(row[0])
        if record.get("is_fixture"):
            fail(f"fixture evidence version cannot be cited by the real trial: {reference}")
        item = projection("evidence", record)
        item["version_id"] = reference
        result.append(item)
    return result


def provider_summary(all_sources, selected_sources, captured_at):
    day = captured_at.date().isoformat()
    gdelt_family = [source for source in all_sources if source.get("adapter") in {"gdelt", "gdelt_gkg"}]
    summaries = []
    for source in selected_sources:
        family = gdelt_family if source.get("adapter") in {"gdelt", "gdelt_gkg"} else [source]
        enabled = [item for item in family
                   if item.get("enabled") and not item.get("deleted")
                   and (item.get("rights") or {}).get("fetch")
                   and (item.get("rights") or {}).get("store")]
        summaries.append({
            "source_id": source["id"],
            "provider": "gdelt" if source.get("adapter") in {"gdelt", "gdelt_gkg"} else source.get("adapter"),
            "provider_requests_today": sum(item.get("requests_today", 0) for item in family
                                           if item.get("budget_date") == day),
            "provider_budget_daily": min((item.get("budget_daily", 0) for item in enabled),
                                         default=source.get("budget_daily", 0)),
            "provider_min_interval_seconds": 6 if source.get("adapter") in {"gdelt", "gdelt_gkg"} else 0,
            "provider_source_ids": sorted(item["id"] for item in family),
            "provider_last_attempt": max((item.get("last_attempt") for item in family
                                          if item.get("last_attempt")), default=None),
        })
    return summaries


def write_exclusive(path, payload):
    if not path.parent.is_dir():
        fail(f"output parent does not exist: {path.parent}")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".trial-snapshot-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            fail(f"refusing to overwrite existing snapshot: {path}")
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--topic-id", action="append", required=True,
                        help="Repeat exactly five times with the real trial topic IDs.")
    parser.add_argument("--reviewer", required=True, help="Actual person performing this check.")
    parser.add_argument("--phase", choices=("start", "daily", "end"), required=True)
    parser.add_argument("--note", default="", help="Optional local context; never inferred by the tool.")
    parser.add_argument("--expected-instance-id")
    parser.add_argument("--trial-start-at", required=True,
                        help="Fixed real-trial T0 as an ISO 8601 timestamp with timezone.")
    parser.add_argument("--start-snapshot", type=Path,
                        help="Required for daily/end: immutable start snapshot that fixes the trial identity.")
    parser.add_argument("--expected-start-sha256",
                        help="Required for daily/end: SHA-256 printed when the start snapshot was created.")
    args = parser.parse_args()

    topic_ids = list(dict.fromkeys(args.topic_id))
    if len(args.topic_id) != 5 or len(topic_ids) != 5:
        fail("exactly five distinct --topic-id values are required")
    if not args.reviewer.strip():
        fail("--reviewer must name the actual checker")
    trial_start_at = timestamp(args.trial_start_at, "--trial-start-at")
    if args.phase == "start" and (args.start_snapshot is not None or args.expected_start_sha256 is not None):
        fail("start phase must not use start-snapshot binding options")
    start_snapshot = None
    start_snapshot_sha256 = None
    if args.phase != "start":
        start_snapshot, start_snapshot_sha256 = load_start_snapshot(args.start_snapshot.expanduser().resolve()
                                                                     if args.start_snapshot else None)
        if (not isinstance(args.expected_start_sha256, str)
                or not len(args.expected_start_sha256) == 64
                or any(character not in "0123456789abcdef" for character in args.expected_start_sha256)
                or start_snapshot_sha256 != args.expected_start_sha256):
            fail("--expected-start-sha256 does not match --start-snapshot")

    data_dir = args.data_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    database = data_dir / "world-insight.sqlite"
    identity_path = data_dir / "instance.json"
    if not database.is_file() or not identity_path.is_file():
        fail("data directory must contain world-insight.sqlite and instance.json")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if args.expected_instance_id and identity.get("instance_id") != args.expected_instance_id:
        fail("instance_id does not match --expected-instance-id")
    normalized_trial_start = trial_start_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if start_snapshot:
        fixed = {
            "data_dir": str(data_dir),
            "instance_id": identity.get("instance_id"),
            "topic_ids": topic_ids,
            "reviewer": args.reviewer.strip(),
            "trial_start_at": normalized_trial_start,
        }
        observed = {key: start_snapshot.get(key) for key in fixed}
        if observed != fixed:
            fail("daily/end trial identity does not match --start-snapshot")

    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=15)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("BEGIN")
        db.execute("SELECT count(*) FROM sqlite_master").fetchone()
        captured_at = datetime.now(timezone.utc)
        if trial_start_at > captured_at:
            fail("--trial-start-at cannot be in the future")
        elapsed_seconds = (captured_at - trial_start_at).total_seconds()
        if args.phase == "start" and elapsed_seconds > 15 * 60:
            fail("start snapshot must be captured within 15 minutes of --trial-start-at")
        if args.phase == "end" and elapsed_seconds < 7 * 24 * 60 * 60:
            fail("end snapshot requires at least 168 real hours since --trial-start-at")
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            fail("database quick_check failed")
        schema_version = db.execute("PRAGMA user_version").fetchone()[0]
        logical_current_version_mismatches = db.execute(
            "SELECT count(*) FROM records r LEFT JOIN versions v "
            "ON r.kind=v.kind AND r.id=v.id AND r.version=v.version "
            "WHERE v.id IS NULL OR v.data!=r.data"
        ).fetchone()[0]
        if args.phase == "start" and logical_current_version_mismatches:
            fail("start snapshot found records that do not match their current immutable versions")
        rows = current_records(db)
        all_rows = current_records(db, include_deleted=True)
        by_kind = {}
        for kind, record in rows:
            by_kind.setdefault(kind, []).append(record)
        all_by_kind = {}
        for kind, record in all_rows:
            all_by_kind.setdefault(kind, []).append(record)
        topics_by_id = {record["id"]: record for record in all_by_kind.get("topic", [])}
        missing = [topic_id for topic_id in topic_ids if topic_id not in topics_by_id]
        if missing:
            fail("missing topic IDs: " + ", ".join(missing))
        topics = [topics_by_id[topic_id] for topic_id in topic_ids]
        fixtures = [topic["id"] for topic in topics if topic.get("is_fixture")]
        if fixtures:
            fail("fixture topics cannot be used for the real trial: " + ", ".join(fixtures))
        if args.phase == "start":
            inactive = [topic["id"] for topic in topics
                        if topic.get("deleted") or topic.get("status") != "active" or not topic.get("followed")]
            if inactive:
                fail("start snapshot requires five active, followed topics: " + ", ".join(inactive))
            implicit_sources = [topic["id"] for topic in topics if not topic.get("source_ids")]
            if implicit_sources:
                fail("start snapshot requires explicit source_ids for every topic: " + ", ".join(implicit_sources))

        topic_set = set(topic_ids)
        selected_raw = {
            kind: [record for record in by_kind.get(kind, [])
                   if relevant(kind, record, topic_set, topics)]
            for kind in AUDIT_FIELDS
        }
        fixture_records = [f"{kind}:{record['id']}" for kind, records in selected_raw.items()
                           for record in records if record.get("is_fixture")]
        if fixture_records:
            fail("fixture records cannot be used for the real trial: " + ", ".join(fixture_records))
        selected = {kind: [projection(kind, record) for record in records]
                    for kind, records in selected_raw.items()}
        citations = citation_versions(db, evidence_references(selected_raw))
        selected_pairs = {(kind, record["id"]) for kind, records in selected.items() for record in records}
        selected_ids = {record_id for _, record_id in selected_pairs}
        version_counts = {}
        if selected_ids:
            placeholders = ",".join("?" for _ in selected_ids)
            for kind, record_id, count in db.execute(
                    f"SELECT kind,id,count(*) FROM versions WHERE id IN ({placeholders}) GROUP BY kind,id",
                    tuple(sorted(selected_ids))):
                if (kind, record_id) in selected_pairs:
                    version_counts[f"{kind}:{record_id}"] = count

        topic_fields = ("id", "version", "question", "status", "followed", "source_ids", "regions", "actors",
                        "country_codes", "time_range", "keywords", "exclude_keywords", "rationale", "coverage_gaps",
                        "reading_baseline", "deleted", "updated_at")
        topic_history = projected_history(db, "topic", topic_set, topic_fields, trial_start_at)
        source_ids = {source_id for topic in topics for source_id in topic.get("source_ids", [])}
        source_ids.update(source_id for topic in topic_history for source_id in topic.get("source_ids", []))
        if start_snapshot:
            source_ids.update(source["id"] for source in start_snapshot.get("sources", []) if source.get("id"))
        for evidence in selected["evidence"]:
            if evidence.get("source_id"):
                source_ids.add(evidence["source_id"])
        for observation in selected["observation"]:
            if observation.get("source_id"):
                source_ids.add(observation["source_id"])
        for citation in citations:
            if citation.get("source_id"):
                source_ids.add(citation["source_id"])
        topic_jobs = [job for job in all_by_kind.get("collection_job", [])
                      if job.get("topic_id") in topic_set]
        source_ids.update(job.get("source_id") for job in topic_jobs if job.get("source_id"))
        sources_by_id = {source["id"]: source for source in all_by_kind.get("source", [])}
        missing_sources = sorted(source_ids - set(sources_by_id))
        if missing_sources:
            fail("missing source IDs: " + ", ".join(missing_sources))
        if args.phase == "start":
            automatic_adapters = {"rss", "gdelt", "gdelt_gkg", "world_bank"}
            without_live_source = []
            for topic in topics:
                topic_sources = [sources_by_id[source_id] for source_id in topic.get("source_ids", [])]
                if not any(not source.get("deleted") and source.get("enabled")
                           and source.get("adapter") in automatic_adapters
                           and (source.get("rights") or {}).get("fetch")
                           and (source.get("rights") or {}).get("store")
                           for source in topic_sources):
                    without_live_source.append(topic["id"])
            if without_live_source:
                fail("start snapshot requires an enabled automatic source for every topic: "
                     + ", ".join(without_live_source))
        sources = []
        source_fields = ("id", "version", "name", "adapter", "domain", "enabled", "status", "budget_daily",
                         "requests_today", "budget_date", "interval_seconds", "last_attempt", "last_success",
                         "data_as_of", "next_check", "last_result_count", "last_error", "last_error_code",
                         "coverage_gaps", "license_url", "checked_at", "rights", "retention_days", "config",
                         "deleted", "updated_at")
        for source in all_by_kind.get("source", []):
            if source["id"] in source_ids:
                sources.append({key: source.get(key) for key in source_fields})
        jobs = []
        job_fields = ("id", "version", "source_id", "topic_id", "scope_signature", "state", "attempts", "request_count",
                      "last_success", "data_as_of", "covered_until", "last_result_count", "next_attempt",
                      "last_error", "error_code", "checkpoint", "gap_start", "gap_end", "coverage_gaps", "deleted",
                      "updated_at")
        for job in all_by_kind.get("collection_job", []):
            if job.get("topic_id") in topic_set or (job.get("topic_id") is None
                                                     and job.get("source_id") in source_ids):
                jobs.append({key: job.get(key) for key in job_fields})
        source_history = projected_history(
            db, "source", {source["id"] for source in sources}, source_fields, trial_start_at
        )
        job_history = projected_history(
            db, "collection_job", {job["id"] for job in jobs}, job_fields, trial_start_at
        )
        fixture_history = historical_fixtures(
            db,
            selected_pairs
            | {("topic", topic_id) for topic_id in topic_ids}
            | {("source", source_id) for source_id in source_ids}
            | {("evidence", citation["id"]) for citation in citations},
        )
        if fixture_history:
            fail("historical fixture records cannot be used for the real trial: " + ", ".join(fixture_history))

        acquisitions = []
        evidence_ids = ({record["id"] for record in selected["evidence"]}
                        | {record["id"] for record in citations})
        acquisition_fields = ("id", "version", "evidence_id", "evidence_version_id", "source_id",
                              "source_version", "job_id", "job_version", "collected_at", "received_at")
        for receipt in by_kind.get("evidence_acquisition", []):
            if receipt.get("evidence_id") in evidence_ids:
                if receipt.get("is_fixture"):
                    fail("fixture acquisition receipts cannot be used for the real trial")
                acquisitions.append({key: receipt.get(key) for key in acquisition_fields})

        per_topic = {}
        for topic in topics:
            topic_id = topic["id"]
            per_topic[topic_id] = {
                kind: sum(1 for record in records if relevant(kind, record, {topic_id}, [topic]))
                for kind, records in selected.items()
            }
        counts = {kind: len(records) for kind, records in selected.items()}
        runtime_path = data_dir / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.is_file() else None
        if args.phase == "start" and runtime is None:
            fail("start snapshot requires runtime.json from the running trial instance")
        if runtime and (runtime.get("instance_id") != identity.get("instance_id")
                        or Path(runtime.get("data_dir", "")).resolve() != data_dir):
            fail("runtime.json does not match the selected data directory and instance_id")
        runtime_process_alive = process_alive(runtime.get("pid")) if runtime else False
        if args.phase == "start" and not runtime_process_alive:
            fail("start snapshot requires a live runtime PID")
        runtime_health = local_health(runtime) if args.phase == "start" else None
        runtime_started_at = timestamp(runtime["started_at"], "runtime started_at") if runtime else None
        if args.phase == "start" and runtime_started_at > trial_start_at:
            fail("--trial-start-at cannot predate the running trial process")
        program_root = Path(runtime["root"]).resolve() if runtime and runtime.get("root") else None
        program_commit = git_commit(program_root) if program_root and program_root.is_dir() else None
        program_clean, program_dirty_count = git_clean(program_root) if program_root and program_root.is_dir() else (None, None)
        if args.phase == "start" and (not program_commit or program_clean is not True):
            fail("start snapshot requires a clean Git program root with a resolvable commit")
        if start_snapshot and start_snapshot.get("program_root") != str(program_root):
            fail("running program root does not match --start-snapshot")
        snapshot_tool_commit = git_commit(ROOT)
        providers = provider_summary(all_by_kind.get("source", []), sources, captured_at)
        canonical = json.dumps(
            {"topics": topics, "topic_history": topic_history, "selected": selected,
             "sources": sources, "jobs": jobs,
             "source_history": source_history, "job_history": job_history,
             "providers": providers, "citations": citations, "acquisitions": acquisitions},
            ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        payload = {
            "schema": SCHEMA,
            "phase": args.phase,
            "actual_seven_day_trial_complete": False,
            "captured_at": captured_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "trial_start_at": trial_start_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "trial_elapsed_seconds": elapsed_seconds,
            "minimum_168h_elapsed": elapsed_seconds >= 7 * 24 * 60 * 60,
            "start_snapshot": str(args.start_snapshot.expanduser().resolve()) if args.start_snapshot else None,
            "start_snapshot_sha256": start_snapshot_sha256,
            "history_window": "For each selected source/job, include the last baseline version before trial_start_at plus every version at or after it.",
            "reviewer": args.reviewer.strip(),
            "note": args.note,
            "git_commit": program_commit,
            "program_root": str(program_root) if program_root else None,
            "program_git_commit": program_commit,
            "program_git_worktree_clean": program_clean,
            "program_git_dirty_entry_count": program_dirty_count,
            "snapshot_tool_root": str(ROOT),
            "snapshot_tool_git_commit": snapshot_tool_commit,
            "schema_version": schema_version,
            "database_quick_check": integrity,
            "logical_current_version_mismatches": logical_current_version_mismatches,
            "sqlite_snapshot_boundary": "Read transaction established before captured_at; all database rows are from that fixed snapshot or earlier.",
            "data_dir": str(data_dir),
            "instance_id": identity.get("instance_id"),
            "runtime_present": runtime is not None,
            "runtime_process_alive": runtime_process_alive,
            "runtime_health": runtime_health,
            "runtime": runtime,
            "topic_ids": topic_ids,
            "topics": [{key: topic.get(key) for key in
                        ("id", "version", "question", "status", "followed", "source_ids", "regions", "actors",
                         "country_codes", "time_range", "keywords", "exclude_keywords", "rationale", "coverage_gaps",
                         "reading_baseline", "updated_at")}
                       for topic in topics],
            "topic_version_history": topic_history,
            "sources": sources,
            "provider_budgets": providers,
            "source_version_history": source_history,
            "collection_jobs": jobs,
            "collection_job_version_history": job_history,
            "counts": counts,
            "per_topic_counts": per_topic,
            "job_states": dict(sorted(Counter(job.get("state") or "unknown" for job in jobs).items())),
            "records": selected,
            "citation_versions": citations,
            "acquisition_receipts": acquisitions,
            "version_history_counts": version_counts,
            "selected_state_sha256": hashlib.sha256(canonical).hexdigest(),
            "end_sample_readiness": {
                "evidence_50": counts["evidence"] >= 50,
                "claims_and_events_20": counts["claim"] + counts["event"] >= 20,
                "judgments_10": counts["judgment"] >= 10,
            },
            "human_fields_still_required": [
                "actual Mac running, sleep and network intervals",
                "upstream success, failure, duplicate and latency interpretation",
                "manual corrections and judgment revisions",
                "elapsed time to find a key change and its change ID",
                "later discovered omissions",
                "end-of-trial item-by-item structural review decisions",
            ],
            "boundary": "One read-only point-in-time snapshot. It does not prove seven continuous days, semantic accuracy, user efficiency, or completion of the required 50/20/10 human review.",
        }
        db.execute("COMMIT")
    finally:
        db.close()
    write_exclusive(output, payload)
    output_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({
        "status": "captured",
        "output": str(output),
        "phase": args.phase,
        "instance_id": payload["instance_id"],
        "topic_count": len(topic_ids),
        "counts": counts,
        "output_sha256": output_sha256,
        "actual_seven_day_trial_complete": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
