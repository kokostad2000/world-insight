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
