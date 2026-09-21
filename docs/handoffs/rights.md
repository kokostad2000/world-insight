# Evidence read and ordinary-export permission handoff

2026-09-21; `dev/ops`, independent `.worktrees/ops`; main merged through `a8679c6`, including required `ad5e32f`. No shared route, platform, contracts or UI files were modified by this owner.

## Changed paths

- `server/modules/knowledge/rights.py`: new pure policy/context and presentation helpers.
- `tests/test_core_rights.py`: real isolated SQLite fixtures for source/evidence permissions, history, deadlines, collector retention and preservation of user work.
- This handoff.

## Finding and interfaces

The existing `knowledge._present` inspects the supplied Evidence's declared rights; `research._evidence_view` additionally intersects current Evidence rights. Neither previously evaluated current/historical Source permissions, removed historical channels, or actual expiry at request time. Both could leave fingerprints visible when body was withheld. The new helper is not yet wired into those routes in this commit.

Public pure functions:

```python
from server.modules.knowledge.rights import build_policy_context, effective_policy, present_evidence

# Root should read snapshots and the requested records in one Store transaction.
# All historical sources/evidence/authored references are necessary, not just a page.
context = build_policy_context(store.snapshots(), now=store.now())
decision = effective_policy(record, context, action="display")
view = present_evidence(record, context, action="export")
```

`build_policy_context(snapshots, sources=None, settings=None, now=None)` invokes the real lifecycle retention evaluator once and indexes only policy facts. Optional `sources` adds current source policy; optional settings overrides the persisted `retention_settings/default` record for trusted internal evaluation. Production callers should use real current time. Contexts must be fresh per request and must never be cached across writes/requests or used for a newer record version. No helper reads or writes Store directly or changes its inputs. Contexts contain no licensed body or user notes.

`effective_policy(record, context, action="display")` returns:

- `rights`: the conservative scope intersection for fetch/store/display/export/ai, expressed as `False`, `metadata`, `excerpt`, or `full`; absent/unknown/invalid values deny body permission.
- `content_allowed`, `content_expired`, `content_expires_at`, `retention_days`, `source_ids`, `action`, `evaluated_at`.
- `reasons`: concrete denial explanations with source ID, limiting historical version, action and scope where applicable. `historical_source_rights` explicitly explains why a later broader licence does not revive a previously restricted source version.

`present_evidence(record, context, action="display")` returns a deep copy. It retains declared `rights` for truthful version history, adds `effective_rights`, `content_policy`, `content_expires_at`, and exact `version_id`. A denied decision clears excerpt, translation and fingerprint together, sets `content_restricted`, and for export sets `export_content_omitted`. It also strips those same content fields from legacy nested channel copies. Authored notes, metadata, IDs and version references remain intact, including for trashed Evidence.

## Policy boundaries

- Requested Evidence rights intersect the latest Evidence rights. All historical primary/channel source identities remain relevant, even when a later edit removes them. Source historical permissions remain conservatively intersected; source retention uses the shortest registered term.
- Historical transitive original-evidence relationships preserve upstream source restrictions and their earlier first collection boundary. Missing original/source policy and invalid provenance cycles fail closed. Only the built-in `manual` source alias may have no Source record; it still requires explicit Evidence permission. URL-only channels without a registered source do not manufacture a licence.
- Full-body content needs full permission. An excerpt grant does not silently permit a record marked `content_scope=full`.
- Source caps apply to manually edited/noted/cited materials too. Actual overdue collector candidates are hidden immediately, even before asynchronous physical cleanup. Historical notes and authored references protect otherwise unbounded candidates, consistently with lifecycle evaluation.
- Physical `content_expired` markers cannot be cleared by a later historical version. No read helper changes stored data or pretends that serialization has physically erased it.
- **Ordinary research exports retain legally exportable, unexpired finite-term content and include its deadline.** They are distinct from backup/recovery snapshots, which proactively omit bounded-source bodies. Expired content is removed from display and ordinary exports.
- Missing/null `retention_days` does not invent a deadline. A finite cap with no reliable first collection timestamp denies body access because validity cannot be established. Invalid source retention policy raises the existing lifecycle error before returning content.

## Executed tests and remaining integration

`python3 -m unittest tests.test_core_rights -v`: initial **20 passed in 0.104s**. After merging the latest main, initial combined rights/lifecycle/platform/backup run: **52 passed in 1.469s**. Two additional source-policy tests then cover metadata-only source versus manual excerpt and separately supplied latest source permissions.

Final command `python3 -m unittest tests.test_core_rights tests.test_lifecycle tests.test_lifecycle_platform tests.test_ops_retention -q`: **54 passed in 1.397s**, exit 0. This includes 22 new rights cases and 32 actual lifecycle/platform/backup regression cases. `git diff --check` passed.

Fixtures use temporary databases and no network provider, running service or occupied port; reserved ops port 8874 was not needed for these pure helpers. No real-source licence review or seven-day observation is claimed.

Root must wire the helper into Evidence list/detail/history/version responses, mutation response serialization as appropriate, ordinary topic bundle Evidence/citations/history, and JSON/Markdown export. Build one context per request/bundle within a consistent Store transaction rather than once per returned row. Root may also use it to unify lifecycle export permission checks while preserving the stricter backup/recovery bounded-content policy. Source lookup/retention at ingestion is outside this read-only helper's scope.

HTTP/browser response non-leakage, root route integration, search-side-channel behavior and 20,000-record performance after integration remain unverified here. Searches should operate over the sanitized representation if body matches can reveal material the caller cannot display. This helper itself is validated only with isolated SQLite and actual policy functions.

Merge order: latest root platform/lifecycle through `ad5e32f` (included), this helper commit, root-owned route integration plus integration tests. Existing `ce94809` candidate-backup tests are included on this branch; root should retain them.
