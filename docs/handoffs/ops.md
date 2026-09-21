# M7 local operations handoff

2026-09-20；独立 worktree `.worktrees/ops`，branch `dev/ops`。基于 main 5e91a85（含 shutdown 修复、sources 维护检查）。

## Changed paths

- `ops/runtime.py`: config/preflight, identity-bound lifecycle, pending startup recovery, selected-program binding, logging and operation lock.
- `ops/backup.py`: online SQLite snapshot, whitelisted attachments/config, manifest verification, staged restore, replacement recovery points.
- `ops/update.py`: explicit local Git release preparation, dirty-worktree protection, maintenance/stop/backup/migrate/health/switch transaction, paired rollback, new-write protection, interrupted-update recovery.
- `ops/cli.py`: one local CLI shared by all shell/double-click entries.
- `scripts/{run-ops,start,stop,status,check-config,backup,restore,update}.sh`, `start.command`, `stop.command` (all executable).
- `README.md`, `.env.example`, `docs/LOCAL_OPERATIONS.md`.
- `tests/test_ops_lifecycle.py`, `docs/evidence/ops-lifecycle.txt`, `docs/evidence/ops-environment.json`, this handoff.

No platform, app, shared contract, migration registry or requirements.lock changes by this owner. Runtime filesystem controls do not mutate another module's domain entities.

## API / operational interface

- First new data creation: `scripts/start.sh --init`; optional `--data-dir`, `--port`, `--no-browser`, `--no-scheduler`. `.env` is created only if absent. Existing identity with missing database is blocked.
- `scripts/check-config.sh [--init]`: local checks, categorized pass/warning/block, nonzero on blocker. Explicit `--probe-network --probe-sources rss,world_bank,gdelt` delegates to sources probe; never implicitly calls a network provider. Python3.11 required; missing Git/curl warns for corresponding feature.
- Start reads external data `active-program.json`; repeated start checks pid/data/instance/root/port and reuses exactly the existing service. Stop uses verified runtime or persisted `pending-start.json` with exact process command ownership; never kills a mere port occupant.
- `scripts/backup.sh [--output new-path]` -> `.wibackup` zip with DB/allowed attachments/instance/non-secret config and manifest. Always verifies contents/counts/schema/references before rename from `.partial`; never overwrites an existing backup. Default excludes `.env`, credentials, logs/cache/runtime/active program selection.
- `scripts/restore.sh package [--data-dir path]`: preview only; `--apply` for empty destination, `--apply --replace` for an explicitly selected existing bound instance; target must be stopped. Existing unbound personal files are blocked even with replace. Existing state is backed up and moved to retained recovery point before installation. `--start-after` optional.
- `scripts/update.sh --target <local-ref> [--dry-run]`: no fetch/push. Source tracked/untracked dirty state blocks. Target archived to immutable sibling release dir, dependency/schema preflight before data writes; maintenance/normal stop/backup precede target migration/HTTP health/topic/read/integrity checks. Switch persists active-program selection. Failures restore old DB+attachments and old program selection; original checkout remains intact.
- `--recover <ID>` explicitly recovers an interrupted update using retained maintenance/transaction log and pending startup PID, including interruption before runtime.json exists.
- `--rollback <ID>` first backs up current state, then refuses any post-update research writes; with no newer data can restore old paired state. No automatic old-snapshot overwrite after newer records.

## Actually executed

`python3 -m unittest tests.test_ops_lifecycle -v` -> **17 passed in 21.296s**, exit 0. Actual Mac CPython processes, SQLite and HTTP; full test names/evidence in `docs/evidence/ops-lifecycle.txt`. Platform details in `ops-environment.json`.

Includes: actual scripts and `.command` executed from Chinese/space paths; duplicate PID reuse; stop/restart and continuing edits; occupied port; actual chmod directory denial; online backup with persisted reading state; empty restore and history+attachment+judgment edit via HTTP; corrupted/manifest-tampered/incompatible backup refusal; existing replacement recovery point and unbound-file protection; dirty tracked/untracked update protection; actual valid migration schema1→2 and explicit paired rollback; actual invalid SQL migration rollback and unhealthy target rollback; updater SIGKILL during controlled migration pause, pending child ownership cleanup and explicit recovery; source program relocation with same data; post-update new-write refusal and preserved current backup. Disk-full/Python absence are injected fault conditions; no physical disk exhaustion claim.

Compilation passed. First sandbox run could not bind sockets, authorized outside-sandbox local-service run used thereafter. A real TIME_WAIT preflight false-positive was found and fixed, then repeated restarts passed. Fixtures, test repositories, databases and processes are isolated; collectors disabled and no upstream requests performed.

## Not verified / integration required

- Browser page inspection/edit after recovery and Finder GUI double-click remain root integration tasks; `.command` execution from shell is not Finder UI verification.
- Real sleep/resume/upstream gap recovery belongs to sources plus M4 observation; no seven-day activity fabricated.
- Physical power loss and actual full disk were not induced; interrupted updater/SQL migration and injected disk write failure provide bounded failure-path coverage.
- Linux/Windows/container platforms and future third-party dependency upgrades are unverified. Current lock is stdlib-only; unsupported target dependency manifests stop before data changes.
- Actual network probe itself was not rerun here; sources owner/root supply their separate real-source report.
- Automatic retention removal is intentionally absent; user recovery points are retained.

## Merge order

1. Root platform shutdown fix and sources maintenance guards (already included through 5e91a85).
2. This M7 commit.
3. Root run full integration tests and browser restore/update acceptance from a clean code snapshot (the update guard correctly rejects a dirty active development worktree). Use isolated data/ports and keep fixture labels.
4. Keep PRD M4 seven-day observation pending; only engineering/Mac execution evidence above is claimed.

## Latest platform integration and final run

Merged latest root `a4622f9` (includes `37bd113` strict platform references and current UI). Backup read-only integrity now additionally checks topic/source (manual built-in allowed)/origin/evidence_alias/read_state and exact judgment/change versions, matching the current Store integrity boundary without migrating a backup during preview.

Final actual command `python3 -m unittest tests.test_ops_lifecycle -v` captured verbatim in `docs/evidence/ops-strict-integrity-tests.txt`: **19 passed in 23.319s**, exit 0. Added rejection of evidence_alias orphan during backup and fabricated nonexistent read_state version during restore before touching the existing target. All prior 17 process/lifecycle tests passed again under the latest platform. This result supersedes the earlier total for final integration; earlier evidence is retained.

## 2026-09-21 retention and independent review corrections

Changed paths: `ops/backup.py`, `ops/update.py`, `tests/test_ops_lifecycle.py`, new `tests/test_ops_retention.py`, this handoff and raw ops test evidence. Base `bea9f0b` includes root lifecycle foundations; no shared/platform/domain files changed here.

Public helper `ops.backup.sanitize_snapshot(path, policy_source=None, observed_at=None)` sanitizes an independent SQLite copy, never the active DB. It preserves notes, metadata, IDs, exact version citations and record/version counts; `excerpt`, `translation`, and `content_fingerprint` are omitted across **all** evidence versions whenever the material has a registered finite source limit. Source-history policies and optional existing-destination policies are combined conservatively. Unknown/missing `retention_days` never invents a limit; a missing source fails existing strict integrity. Invalid nonnull limits reject the package.

The sanitizer runs on online backup snapshots, after legacy package checksum/reference verification, and before restoration data replacement. Successfully retained direct recovery points are also sanitized. Secure deletion and VACUUM remove old body bytes from SQLite freelist/unused pages. Source-limited archives are explicitly metadata-and-user-notes recovery packages; they are not full-text backups. Manifest `content_policy` states omitted evidence IDs/fields, bounded source policies, counts and legacy behavior. Restore preview/result adds `content_policy`; `unpack_verified` adds `restoration_content_policy` and the post-sanitization SQLite hash, while verifying the original archive manifest first. Default unbounded sources retain legal contents. `backup_content_omitted`/reason fields distinguish deliberately omitted content from an originally empty excerpt.

Root hookup required: call `sanitize_snapshot(checkpoint_path, policy_source=current_db_path)` after closing migration-generated `migration-before-*.sqlite` copies. This owner did not modify platform migration registry. The pure domain `knowledge.lifecycle.evaluate_retention(snapshots,sources,settings,now)` is dynamically used when present for due collector candidates; if actual collector records exist but the evaluator is unavailable, backup explicitly stops rather than silently archiving expired candidates. The evaluator has not landed on this branch at this handoff, so actual candidate-policy integration still requires the lifecycle commit and focused verification. Finite-source policy is already fully tested independently.

Independent review fixes:

- Update rollback now uses version-2 `data_fingerprint`: DB records/versions/schema plus every attachment relative path and SHA256 content. Hash/read failures, additions, deletions, content changes and file changes during hashing block rollback. The complete fingerprint is rechecked after stopping. Older update records without an attachment baseline are explicitly refused after preserving current state; no unsafe fallback to DB-only checks.
- Restore blocks when `maintenance.json` exists or an actual `pending_runtime` startup is live, including before treating the destination as idle. Messages direct users to `update.sh --recover <ID>` or `stop.sh`. Idle ownership is rechecked immediately before replacement.

Executed `python3 -m unittest tests.test_ops_lifecycle tests.test_ops_retention -v` on actual Mac: **29 passed in 29.205s**. Raw output: `docs/evidence/ops-retention-review-tests.txt`. Added real subprocess cases for pending startup and maintenance restore refusal; attachment-only changes/new paths, a change during stop, and hash-read failure all preserve current data. Six real SQLite/package cases verify old and latest finite-source content absent from the raw archive/restored database bytes, preserved notes/references/manifest hashes, default unbounded content, legacy old-package sanitization, stricter current policy, direct recovery-point sanitization, invalid-policy rejection and standalone migration snapshot helper. No real-source/sleep/Finder claims added.

Merge this commit after `bea9f0b`, then merge lifecycle pure evaluator and root migration hookup, and run the targeted combined lifecycle/backup tests. Main retains M4 pending real observation.

## Actual candidate lifecycle / backup integration (after 114ab8d)

Merged `dev/lifecycle` commit `114ab8d`, then changed only `tests/test_ops_retention.py` and this handoff. No ops implementation change was necessary: the real `evaluate_retention(snapshots,sources,settings,now)` interface works with the snapshot sanitizer.

Executed `python3 -m unittest tests.test_ops_retention tests.test_lifecycle tests.test_lifecycle_platform -v`: **32 passed in 1.292s**, exit 0. New four integration cases use actual Store/SQLite/archive/restore logic and the actual lifecycle evaluator; the collector's historical first collection date is an explicit fixture, not a claim of real elapsed observation:

1. An unreferenced, untouched collector candidate beyond 90 days loses old and current body/translation bytes in the backup while the original active database remains unchanged and all version IDs are preserved.
2. A legacy archive containing the same expired candidate is sanitized before restoration; subsequent real `knowledge.ingest(..., origin="collector")` cannot reinsert its body. Raw SQLite bytes do not contain old, current or attempted-refetch body tokens.
3. A historical manual note protects an otherwise old unbounded collector candidate even when a legacy fixture clears its latest notes and manually_touched flag. The note and all legal historical/current body contents survive backup and restoration.
4. A persisted disabled candidate-retention setting preserves unbounded candidate content and remains disabled after restoration.

This closes the prior handoff's unverified actual candidate-evaluator integration item. Root's platform migration-checkpoint hookup is still a separate pending root change at this moment; the independently callable sanitizer was already tested with a real SQLite migration-style snapshot. No network, browser, Finder, actual elapsed seven-day retention or real-source claim was added.
