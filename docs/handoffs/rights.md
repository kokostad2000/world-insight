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

`build_policy_context(snapshots, sources=None, settings=None, now=None)` invokes the real lifecycle retention evaluator once and indexes only policy facts. Optional `sources` adds current source policy; optional settings overrides the persisted `retention_settings/default` record for trusted internal evaluation. Production callers should use real current time. Contexts must be fresh per request and must never be cached across writes/requests or used for a newer record version. No helper reads or writes Store directly or changes its inputs. Contexts contain no licensed body or user notes. Source policies are now scoped to the material's persistence period, as described in the integration addendum below.

`effective_policy(record, context, action="display")` returns:

- `rights`: the conservative scope intersection for fetch/store/display/export/ai, expressed as `False`, `metadata`, `excerpt`, or `full`; absent/unknown/invalid values deny body permission.
- `content_allowed`, `content_expired`, `content_expires_at`, `retention_days`, `source_ids`, `action`, `evaluated_at`.
- `reasons`: concrete denial explanations with source ID, limiting historical version, action and scope where applicable. `historical_source_rights` explicitly explains why a later broader licence does not revive a previously restricted source version.

`present_evidence(record, context, action="display")` returns a deep copy. It retains declared `rights` for truthful version history, adds `effective_rights`, `content_policy`, `content_expires_at`, and exact `version_id`. A denied decision clears excerpt, translation and fingerprint together, sets `content_restricted`, and for export sets `export_content_omitted`. It also strips those same content fields from legacy nested channel copies. Authored notes, metadata, IDs and version references remain intact, including for trashed Evidence.

## Policy boundaries

- Requested Evidence rights intersect the latest Evidence rights. All historical primary/channel source identities remain relevant, even when a later edit removes them. Applicable source historical permissions remain conservatively intersected; source retention uses the shortest term applicable during that material's persistence period.
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

## Actual endpoint and event integration follow-up

Additional ownership explicitly delegated by root: `knowledge/__init__.py`, `research/__init__.py`, `knowledge/lifecycle.py`, `knowledge/policy_period.py`, `knowledge/rights.py`, `ops/backup.py`, new behavioral tests and the old export regression fixture. Main merged through `b88a8b6`, which supplies M2 policy events and root's `knowledge → research → activity` consumer registration. This owner still did not modify `app.py`, Store, contracts or the UI.

- Evidence list (simple/filtered/similar/search), detail, history, and the new `GET /api/evidence/<id>/backlinks` response use one fresh policy context inside one Store transaction. Backlinks returns `{evidence, relations}`; the existing detail relations remain compatible. Search matches the sanitized record so hidden excerpt/translation/fingerprint cannot become an existence oracle.
- Manual create/duplicate/PATCH/correction/split and lifecycle restore responses use the same presentation policy. Split computes one context for both returned records. Expired bodies cannot be persisted again through corrections, and a split keeps the already-expired marker. Authored notes remain intact.
- Collector `ingest(..., origin="collector")` returns a metadata receipt with original identity/version/deduplication/provenance/notes and association fields, empty licensed body/fingerprint, `response_mode="collector_receipt"` and `response_content_omitted=true`. It needs no full-history policy scan per collected item. This is a response policy only; tests separately verify actual authorized content persisted in Store and fixed-version links still work.
- Topic bundle, evidence citations and complete history, JSON export and Markdown export share one context and transaction. Markdown explicitly prints content deadlines and reasons. Source metadata remains allowlisted. Background observations honor explicitly chosen country codes and source IDs even for old collector records linked to the topic; separately authored historical citations remain fixed, and no stored association or country/period is rewritten.
- `knowledge.on_event(store, event)` consumes `source.policy_changed`. All historical primary/channel/original-source links are considered. It preserves declared Evidence rights, creates owner-side review obligations on Evidence/Claim/Event, and publishes deterministic `evidence.updated` events with `dependency_review=true` for research/activity. Review IDs and deterministic outbox IDs make retries idempotent. A failed later consumer rolls back M3 changes atomically. Delayed events do not assign an obsolete pre-material restriction to newly acquired material.

### Source policy periods

New pure `knowledge.policy_period` is shared by read presentation, automatic retention and backup/restore sanitization. `first_saved_at` uses the earliest immutable `first_collected_at`/`created_at`, including original-material history; editable collection timestamps cannot renew it. `applicable_source_versions(history, saved_at)` selects the policy in force before that first persistence plus all later policies. Superseded pre-material defaults, such as a newly created source's initial `rights=false` or an already-replaced old retention cap, do not permanently block or erase later legally acquired materials. Once a restriction applied to an existing material, later broadening does not retroactively remove it. Missing persistence time, unlocatable/non-monotonic source timestamps and equal-time ambiguity retain conservative history.

The actual lifecycle evaluator and `ops.backup.sanitize_snapshot` use the same period rule. Recovery exports remain more restrictive than ordinary research exports: an applicable finite source cap proactively strips body from recovery copies, even before expiry. A pre-material cap that was already replaced no longer strips an otherwise legitimate new body's archive. Existing-destination policies in restoration participate with their original timestamps. Historical original links preserve upstream content limits instead of restarting the clock through copying.

`effective_policy` additionally exposes `source_policy_versions` for an explainable applicable-version set. New tests cover positive permission activation, old restriction persistence, delayed policy delivery, unknown chronology, actual archive extraction/restoration and physical cleanup of only the correct records.

### Final integration validation and boundaries

Executed `python3 -m unittest discover -s tests -q`: **205 tests passed in 33.201 seconds**, exit 0. This includes 14 new actual loopback HTTP/SQLite tests on reserved port 8874, five new source-policy-period/SQLite/archive tests, the existing pure policy cases, and the complete existing M3/M4/M2/lifecycle/M7 regressions. Initial HTTP fixture omissions (`scenario.description`, `observation.unit`) were corrected before this final passing run. The older export regression now asserts the original marker is absent, that the denied write response is empty, and that permitted stored content remains intact, instead of mistakenly searching for an empty response string. No permission rule was weakened to satisfy a test.

New tests: `tests/test_core_access_http.py`, `tests/test_core_policy_period.py`; updated existing fixture: `tests/test_core_domain.py`. Source policy events are exercised through the real M2 PATCH handler and actual root `Application.drain`, including transaction rollback when the next consumer fails and durable retry. The whole suite used isolated temporary data/processes; no live research data, external collection, GitHub push, browser automation or seven-day observation was involved.

Performance boundary: each normal Evidence request or bundle builds the full snapshot context once; page rows, citations and history share it. Collector receipts require zero policy scans. The once-per-request property is asserted in actual HTTP tests, but a new 20,000-material benchmark has not been run by this owner. Full-history deserialization per request remains a measurable capacity risk; a root-owned targeted policy snapshot API may be needed after measurement. Do not describe this correctness run as satisfying capacity or browser acceptance.

Merge after `b88a8b6` (included), then root runs the real browser and capacity acceptance. Root's app consumer registration is already present in the base. Physical recovery copies intentionally omit applicable bounded content; ordinary research export retains unexpired licensed content and declares its deadline.
