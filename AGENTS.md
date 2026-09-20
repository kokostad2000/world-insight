# World Insight development

Read docs/PRD.md, IMPLEMENTATION_PLAN.md, ACCEPTANCE.md and PROGRESS.md before resuming.
PRD milestone M1-M4 is separate from code modules M1-M7. Never mark real seven-day observation complete from fixtures.

Root owns packages/contracts, server/platform, server/app.py, migration registry, dependencies and integration docs. Each parallel writer uses an independent Git worktree, branch, database directory, collector and port. No GitHub push, public deployment, paid services or external messages are authorized.

Module owners only mutate their domain through platform Store; do not write another module's entities. Cross-module communication is a durable outbox consumed idempotently by owners. Ask root before shared-contract changes. No reset/clean or broad staging. Commit only assigned paths.

Every handoff includes changed paths, API changes, executed tests with actual results, unverified matters and merge order. Preserve historical evidence and judgment versions. Unknown is never zero, collection time never event time, reviewed never proven true. All fixtures must be visibly labeled and isolated.
