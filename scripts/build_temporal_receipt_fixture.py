#!/usr/bin/env python3
"""Build an offline retained fixture for browser review of collection receipts."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.modules import knowledge, research, sources
from server.modules.sources import adapters
from server.platform.config import ensure_data, load_config
from server.platform.store import Store


RSS = b'''<rss><channel><item><title>[fixture] Prior-week official release</title>
<link>https://www.federalreserve.gov/fixture/prior-week.htm</link>
<guid>temporal-browser-prior-week</guid>
<pubDate>Mon, 14 Sep 2026 08:00:00 GMT</pubDate>
<description>Fixture-only metadata for collection-time browser acceptance.</description>
</item></channel></rss>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    if args.data_dir.exists() and any(args.data_dir.iterdir()):
        raise SystemExit("refusing non-empty data directory")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(data_dir=args.data_dir, port=8893)
    identity = ensure_data(config, initialize=True)
    store = Store(config["db_path"])
    (args.data_dir / "instance.json").write_text(json.dumps(identity), encoding="utf-8")
    clock = ["2026-09-14T09:00:00.000000Z"]
    store.now = lambda: clock[0]
    try:
        sources.seed_sources(store)
        topic = research.handle(store, "POST", ["topics"], {
            "question": "[离线夹具] 跨周重复收取与原始发布时间",
            "source_ids": ["source-fed"],
            "keywords": ["fixture"],
            "status": "active",
            "followed": False,
            "is_fixture": True,
        }, {})
        sources.enqueue(store, "source-fed", topic["id"])
        first_job = sources.Scheduler(store, fetcher=lambda *_: adapters.Response(200, RSS)).tick(False)
        first = knowledge.handle(store, "GET", ["evidence"], {}, {"topic_id": topic["id"]})["items"][0]
        change_count = len(store.all("change"))

        clock[0] = "2026-09-21T09:00:00.000000Z"
        sources.enqueue(store, "source-fed", topic["id"])
        second_job = sources.Scheduler(store, fetcher=lambda *_: adapters.Response(200, RSS)).tick(False)
        current = knowledge.handle(store, "GET", ["evidence", first["id"]], {}, {})
        topic = research.handle(store, "PATCH", ["topics", topic["id"]], {
            "expected_version": topic["version"], "status": "paused",
        }, {})
        filtered = knowledge.handle(store, "GET", ["evidence"], {}, {
            "topic_id": topic["id"], "time_field": "last_collected_at",
            "since": "2026-09-21T00:00:00+08:00", "until": "2026-09-21T23:59:59+08:00",
        })
        report = {
            "fixture": True,
            "external_requests": 0,
            "topic_id": topic["id"],
            "evidence_id": current["id"],
            "published_at": current["published_at"],
            "first_collected_at": current["first_collected_at"],
            "evidence_collected_at": current["collected_at"],
            "last_collected_at": current["last_collected_at"],
            "evidence_version": current["version"],
            "history_versions": [row["version"] for row in store.history("evidence", current["id"])],
            "acquisition_versions": [row["version"] for row in store.history("evidence_acquisition", current["id"])],
            "first_job_state": first_job["state"],
            "second_job_state": second_job["state"],
            "today_last_collected_total": filtered["total"],
            "change_count_before_and_after_repeat": [change_count, len(store.all("change"))],
        }
        (args.data_dir / "fixture-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        store.close()


if __name__ == "__main__":
    main()
