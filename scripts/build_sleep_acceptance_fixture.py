#!/usr/bin/env python3
"""Prepare an isolated, zero-network AC-36 database for a later real Mac sleep run."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.modules import research, sources
from server.platform.config import ensure_data, load_config
from server.platform.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--port", type=int, default=8897)
    args = parser.parse_args()
    if args.data_dir.exists() and any(args.data_dir.iterdir()):
        raise SystemExit("refusing non-empty data directory")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(data_dir=args.data_dir, port=args.port)
    identity = ensure_data(config, initialize=True)
    store = Store(config["db_path"])
    (args.data_dir / "instance.json").write_text(json.dumps(identity), encoding="utf-8")
    try:
        sources.seed_sources(store)
        for source_id in ("source-gdelt", "source-gdelt-gkg", "source-world-bank"):
            source = store.get("source", source_id)
            sources.handle(store, "PATCH", ["sources", source_id], {
                "expected_version": source["version"], "enabled": False,
            }, {})
        fed = store.get("source", "source-fed")
        fed = sources.handle(store, "PATCH", ["sources", fed["id"]], {
            "expected_version": fed["version"],
            "enabled": True,
            "budget_daily": 4,
            "interval_seconds": 300,
        }, {})
        topic = research.handle(store, "POST", ["topics"], {
            "question": "[隔离睡眠验收] Mac 唤醒后采集器如何记录 RSS 中断区间？",
            "source_ids": [fed["id"]],
            "country_codes": ["USA"],
            "keywords": ["Federal Reserve", "FOMC"],
            "exclude_keywords": [],
            "status": "active",
            "followed": True,
            "is_fixture": True,
        }, {})
        report = {
            "fixture": True,
            "external_requests": 0,
            "actual_sleep_performed": False,
            "data_dir": str(args.data_dir.resolve()),
            "port": args.port,
            "instance_id": identity["instance_id"],
            "topic_id": topic["id"],
            "enabled_collectors": [fed["id"]],
            "budget_daily": fed["budget_daily"],
            "interval_seconds": fed["interval_seconds"],
            "required_sleep_seconds": fed["interval_seconds"] * 2 + 60,
            "status": "prepared_only",
            "next_action": "Start with the scheduler, wait for one successful Fed RSS job, then obtain user approval immediately before an actual Mac sleep longer than required_sleep_seconds.",
        }
        (args.data_dir / "sleep-acceptance-preparation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
