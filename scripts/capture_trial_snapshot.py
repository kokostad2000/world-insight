#!/usr/bin/env python3
"""Capture one read-only, non-overwriting snapshot for the seven-day real trial."""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "world_insight_trial_snapshot/v1"
AUDIT_FIELDS = {
    "evidence": ("id", "version", "title", "source_id", "source_record_id", "published_at",
                 "source_updated_at", "collected_at", "discovered_at", "status",
                 "origin_evidence_id", "topic_id", "topic_ids", "updated_at"),
    "claim": ("id", "version", "subject", "statement", "topic_id", "dispute_status", "evidence_version_ids",
              "attribution", "updated_at"),
    "event": ("id", "version", "title", "topic_id", "event_type", "occurred_at", "time_precision",
              "location", "claim_ids", "evidence_version_ids", "verification_status", "updated_at"),
    "judgment": ("id", "version", "conclusion", "topic_id", "judgment_type", "evidence_version_ids",
                 "opposing_evidence_version_ids", "missing_evidence", "review_date", "status",
                 "reviewer", "updated_at"),
    "scenario": ("id", "version", "title", "topic_id", "evidence_version_ids",
                 "opposing_evidence_version_ids", "review_date", "status", "reviewer", "updated_at"),
    "impact_path": ("id", "version", "title", "topic_id", "status", "reviewer", "updated_at"),
    "review": ("id", "version", "topic_id", "judgment_id", "judgment_version", "outcome",
               "evidence_version_ids", "author", "updated_at"),
    "metric": ("id", "version", "topic_id", "indicator", "country_code", "period",
               "published_at", "source_id", "evidence_version_ids", "updated_at"),
    "change": ("id", "version", "topic_id", "kind", "aggregate_id", "occurred_at", "status",
               "updated_at"),
}


def fail(message):
    raise SystemExit(message)


def current_records(db):
    rows = db.execute("SELECT kind,data FROM records ORDER BY kind,id").fetchall()
    result = []
    for kind, raw in rows:
        record = json.loads(raw)
        if not record.get("deleted"):
            result.append((kind, record))
    return result


def belongs(record, topic_ids):
    return record.get("topic_id") in topic_ids or bool(set(record.get("topic_ids") or []) & topic_ids)


def projection(kind, record):
    return {key: record.get(key) for key in AUDIT_FIELDS[kind]}


def git_commit():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def write_exclusive(path, payload):
    if not path.parent.is_dir():
        fail(f"output parent does not exist: {path.parent}")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fail(f"refusing to overwrite existing snapshot: {path}")
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


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
    args = parser.parse_args()

    topic_ids = list(dict.fromkeys(args.topic_id))
    if len(args.topic_id) != 5 or len(topic_ids) != 5:
        fail("exactly five distinct --topic-id values are required")
    if not args.reviewer.strip():
        fail("--reviewer must name the actual checker")

    data_dir = args.data_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    database = data_dir / "world-insight.sqlite"
    identity_path = data_dir / "instance.json"
    if not database.is_file() or not identity_path.is_file():
        fail("data directory must contain world-insight.sqlite and instance.json")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if args.expected_instance_id and identity.get("instance_id") != args.expected_instance_id:
        fail("instance_id does not match --expected-instance-id")

    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=15)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA busy_timeout=15000")
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            fail("database quick_check failed")
        schema_version = db.execute("PRAGMA user_version").fetchone()[0]
        db.execute("BEGIN")
        rows = current_records(db)
        by_kind = {}
        for kind, record in rows:
            by_kind.setdefault(kind, []).append(record)
        topics_by_id = {record["id"]: record for record in by_kind.get("topic", [])}
        missing = [topic_id for topic_id in topic_ids if topic_id not in topics_by_id]
        if missing:
            fail("missing topic IDs: " + ", ".join(missing))
        topics = [topics_by_id[topic_id] for topic_id in topic_ids]
        fixtures = [topic["id"] for topic in topics if topic.get("is_fixture")]
        if fixtures:
            fail("fixture topics cannot be used for the real trial: " + ", ".join(fixtures))
        if args.phase == "start":
            inactive = [topic["id"] for topic in topics
                        if topic.get("status") != "active" or not topic.get("followed")]
            if inactive:
                fail("start snapshot requires five active, followed topics: " + ", ".join(inactive))

        topic_set = set(topic_ids)
        selected_raw = {
            kind: [record for record in by_kind.get(kind, []) if belongs(record, topic_set)]
            for kind in AUDIT_FIELDS
        }
        fixture_records = [f"{kind}:{record['id']}" for kind, records in selected_raw.items()
                           for record in records if record.get("is_fixture")]
        if fixture_records:
            fail("fixture records cannot be used for the real trial: " + ", ".join(fixture_records))
        selected = {kind: [projection(kind, record) for record in records]
                    for kind, records in selected_raw.items()}
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

        source_ids = {source_id for topic in topics for source_id in topic.get("source_ids", [])}
        for evidence in selected["evidence"]:
            if evidence.get("source_id"):
                source_ids.add(evidence["source_id"])
        sources = []
        source_fields = ("id", "version", "name", "adapter", "enabled", "status", "budget_daily",
                         "requests_today", "budget_date", "interval_seconds", "last_attempt", "last_success",
                         "data_as_of", "next_check", "last_error", "coverage_gaps", "updated_at")
        for source in by_kind.get("source", []):
            if source["id"] in source_ids:
                sources.append({key: source.get(key) for key in source_fields})
        jobs = []
        job_fields = ("id", "version", "source_id", "topic_id", "state", "attempts", "request_count",
                      "last_success", "data_as_of", "covered_until", "last_result_count", "next_attempt",
                      "last_error", "coverage_gaps", "updated_at")
        for job in by_kind.get("collection_job", []):
            if job.get("topic_id") in topic_set or (job.get("topic_id") is None and job.get("source_id") in source_ids):
                jobs.append({key: job.get(key) for key in job_fields})

        acquisitions = []
        evidence_ids = {record["id"] for record in selected["evidence"]}
        acquisition_fields = ("id", "version", "evidence_id", "evidence_version_id", "source_id",
                              "source_version", "job_id", "job_version", "collected_at", "received_at")
        for receipt in by_kind.get("evidence_acquisition", []):
            if receipt.get("evidence_id") in evidence_ids:
                acquisitions.append({key: receipt.get(key) for key in acquisition_fields})

        per_topic = {}
        for topic_id in topic_ids:
            per_topic[topic_id] = {
                kind: sum(1 for record in records if belongs(record, {topic_id}))
                for kind, records in selected.items()
            }
        counts = {kind: len(records) for kind, records in selected.items()}
        canonical = json.dumps(
            {"topics": topics, "selected": selected, "sources": sources, "jobs": jobs,
             "acquisitions": acquisitions}, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        runtime_path = data_dir / "runtime.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.is_file() else None
        payload = {
            "schema": SCHEMA,
            "phase": args.phase,
            "actual_seven_day_trial_complete": False,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "reviewer": args.reviewer.strip(),
            "note": args.note,
            "git_commit": git_commit(),
            "schema_version": schema_version,
            "database_quick_check": integrity,
            "data_dir": str(data_dir),
            "instance_id": identity.get("instance_id"),
            "runtime_present": runtime is not None,
            "runtime": runtime,
            "topic_ids": topic_ids,
            "topics": [{key: topic.get(key) for key in
                        ("id", "version", "question", "status", "followed", "source_ids", "regions",
                         "keywords", "exclude_keywords", "reading_baseline", "updated_at")}
                       for topic in topics],
            "sources": sources,
            "collection_jobs": jobs,
            "counts": counts,
            "per_topic_counts": per_topic,
            "job_states": dict(sorted(Counter(job.get("state") or "unknown" for job in jobs).items())),
            "records": selected,
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
    print(json.dumps({
        "status": "captured",
        "output": str(output),
        "phase": args.phase,
        "instance_id": payload["instance_id"],
        "topic_count": len(topic_ids),
        "counts": counts,
        "actual_seven_day_trial_complete": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
