# Shared contract v1 (root-owned)

HTTP JSON, UTF-8; local-only `127.0.0.1`. API routes do not call paid/AI providers. Root owns routing and shared Store; modules export `handle(store, method, segments, body, query)` and return a JSON-serializable value or `None` when route is not theirs. `segments` excludes `/api`; query is dict of single strings. Domain failures raise `ApiError(status, code, message, details=None)` from `server.platform.errors`.

Collection GET returns `{items, total, offset, limit, data_status, empty_reason}`. Resource GET/POST/PATCH returns the record directly, with `id, version, created_at, updated_at`. POST creates, PATCH requires `expected_version`. Conflict is HTTP 409 and includes current version. No mass silent overwrites. Errors: `{error:{code,message,details}}`. History GET `/api/<collection>/<id>/history` returns `{items:[immutable snapshots]}`. All list limits <= 200.

## Store API (platform-owned)

- `store.create(kind, data, record_id=None)` -> record. Caller may provide record_id for idempotency; duplicate ID returns existing only via explicit domain logic.
- `store.get(kind, id)` -> record or raises 404.
- `store.list(kind, topic_id=None, limit=100, offset=0, search=None)` -> collection.
- `store.all(kind, topic_id=None)` -> list (internal jobs/export, not unbounded API responses).
- `store.find(kind, field, value)` -> list of exact field matches; canonical_url/content_fingerprint/source_record_id indexed. Evidence additionally supports topic_ids[]; list/all(topic_id) matches primary or additional association.
- `store.update(kind, id, data, expected_version)` merges patch, increments version; required optimistic conflict control.
- `store.history(kind,id)` -> list of immutable snapshots (version ascending).
- `store.version(version_id)` -> immutable evidence snapshot. ID is `<evidence_id>@<version>`.
- `store.transaction()` -> context manager for one SQLite transaction, nested operations join it.
- `store.publish(event_type, aggregate_id, payload, event_id=None)` durable transactional outbox, returns event id. Consumer acknowledgment is platform-owned.
- `store.now()` UTC ISO timestamp; `store.path` database pathlib.Path; `store.data_dir` parent path.
- Entities are immutable versions with indexed latest records. `topic_id` nullable; unlink changes current association, never deletes record/history.

Only entity owner validates & writes its kinds. Generic storage isn't permission to modify another module's domain. Root composes cross-module operations using public module functions. Collector calls knowledge `ingest(store, data)`; research consumer `on_event(store,event)`; activity consumer `on_event(store,event)`. Event shape `{id,type,aggregate_id,payload,created_at}`. Retry keeps event ID; receivers use stable per-event IDs to avoid duplicate effects. Outbox delivery and acknowledgment are atomic.

## Ownership and entity shape

| Kind / HTTP collection | Owner | Required domain fields and semantics |
|---|---|---|
| topic / topics | research | question, regions[], actors[], time_range, keywords[], exclude_keywords[], rationale, status active/paused/archived, followed, reading_baseline |
| evidence / evidence | knowledge | source_id, url, source_record_id, title, excerpt, language, publisher, author, material_type, published_at, source_updated_at, collected_at, discovered_at, status, origin_evidence_id, channels[], content_fingerprint, rights, topic_id |
| claim / claims | knowledge | subject, statement, evidence_version_ids[], attribution, dispute_status, topic_id |
| event / events | knowledge | title, event_type, actors[], occurred_at, time_precision unknown/month/day/instant, location {name,country_code,precision:unknown/country/region/city/coordinate,lat?,lon?}, claim_ids[], evidence_version_ids[], verification_status, topic_id |
| observation / metrics | knowledge | indicator, country_code, value (null != 0), unit, period, published_at, frequency, source_id, evidence_version_ids[], topic_id |
| judgment / judgments | research | topic_id, conclusion, judgment_type explanation/prediction, evidence_version_ids[], opposing_evidence_version_ids[], assumptions[], missing_evidence, confidence low/medium/high, confidence_reason, valid_until, outcome_criteria, review_date, status draft/reviewed/needs_review/withdrawn, author, reviewer, change_reason |
| scenario / scenarios | research | topic_id, title, description, valid_until, assumptions[], evidence_version_ids[], opposing_evidence_version_ids[], counterevidence_search, signals[], invalidation_conditions, review_date, status, change_reason |
| impact_path / impact-paths | research | topic_id, title, nodes[], edges[{from,to,status:observed/assumption/unverified,evidence_version_ids[],note,needs_review}], status, change_reason |
| review / reviews | research | topic_id, judgment_id, judgment_version, outcome meets/does_not_meet/partly_meets/indeterminate, rationale, evidence_version_ids[], author, next_review_date (optional; current-version review clears/replaces due date, never clears needs_review) |
| source / sources | sources | name, adapter, domain, languages[], regions[], license_url, checked_at, rights{fetch,store,display,export,ai}, enabled, budget_daily, interval_seconds, last_attempt,last_success,data_as_of,next_check,status |
| collection_job / sources jobs | sources | source_id, topic_id, checkpoint, attempts, state, request_count, gap_start, gap_end |
| change / changes | activity | event_id, type, aggregate_id, topic_id, title, discovered_at, occurred_at, priority, needs_review, evidence_version_ids[] |
| read_state / changes/read | activity | change_id, change_version, snapshot_at, topic_id, read_at |
| notification / notifications | activity | event_id, topic_id, reason, status, related_id |
| brief / briefs | activity | topic_id, content, evidence_version_ids[], judgment_ids[], status, generated_at |

Unknown fields are null or explicit unknown, never fabricated. Source state: ready/not_configured/disabled/manual/quota_exhausted/failed/stale. Data status: fresh/stale/unknown/unavailable. Coverage: complete/partial/unavailable/not_configured; complete means configured sources checked, not complete world coverage. No matches only when checks succeeded. Status flags for evidence include unverified/reviewed/disputed/corrected/withdrawn/inaccessible/restricted; reviewed is user action, not truth.

Evidence `content_scope` is `excerpt` by default; only explicitly complete, legally stored content (`full`) may use content fingerprint identity. Equal short excerpts or null indicator values never establish identity, and distinct provider record IDs remain distinct. Translation has the same storage/display/export limits as original excerpts. Observation supports topic_ids[] without replacing its original topic association. Instant comparisons normalize time zones; uncertain date/month precision is retained and interval overlap is used for filtering. Withdrawal remains withdrawn after correction, with separate needs_review/review_reason metadata.

## Routes beyond standard CRUD

- `GET /api/health` and `/api/bootstrap` root. Bootstrap includes version,data_dir,capabilities,templates.
- `GET /api/topics/<id>/bundle` research composes via read-only Store: topic,evidence,claims,events,judgments,scenarios,impact_paths,reviews,observations.
- `POST /api/evidence/<id>/corrections` knowledge: expected_version,reason,status (corrected/withdrawn/inaccessible/restricted),substantive:boolean, optional title/excerpt. Only human confirmed substantive changes emit evidence.corrected; format-only changes emit evidence.updated.
- `POST /api/evidence/<id>/split` knowledge: explicit chosen channels, reason, expected_version. Preserve original and emit dependency review event.
- `GET /api/exports?topic_id=...&format=json|markdown` research: JSON bundle or `{filename,content,format}`. Filter rights, include immutable citations and unknowns.
- `POST /api/sources/<id>/refresh` sources schedules work (does not block reads); refresh shares persistent quotas with scheduler and retries. `GET /api/sources/coverage`, `/api/sources/jobs`; optional providers always not_configured.
- `GET /api/dashboard?window=unread|24h|7d|custom&topic_id=&offset=&limit=&since=&until=` activity returns changes collection plus snapshot_at,coverage,topics,review_due,summary. `POST /api/changes/read` body `{snapshot_at,items:[{id,version}]}` only marks submitted visible versions <= snapshot.
- `GET /api/briefs`, `POST /api/briefs {topic_id}`; notifications GET/PATCH. `/api/tracks`, `/api/ai`, `/api/market-data` root return `{status:not_configured,items:[],reason:...}`.

## Events

`evidence.created`, `evidence.updated`, `evidence.corrected`, `event.created`, `claim.created`, `judgment.created`, `judgment.revised`, `research.needs_review`, `source.failed`, `source.recovered`. Payload includes topic_id, object/version ids, title, reason; evidence corrected includes evidence_id and old_version_ids. Root consumers always knowledge, research, then activity. A failure rolls back delivery side effects and remains retryable. Historical judgment snapshots are never rewritten by current review flags.

## P0 lifecycle amendment (root, 2026-09-21)

- Collection Store.list/all/find exclude records with deleted=true by default; include_deleted=True is an explicit recovery scan. Store.get/history/version retain stable identities. Store.snapshots() returns every historical {kind,record}, including deleted records, for dependency checks.
- knowledge.ingest(store,data,origin='manual') accepts keyword-only origin='collector' from M2. Evidence ingest_origin, first_collected_at, manually_touched are internal fields, never caller-editable. Repeated acquisition does not renew first_collected_at or overwrite manual notes. Manual re-registration appends an entered note; exact-identity deletion prevents silent reappearance. Explicit PATCH/correction/split protects the material from candidate cleanup.
- source.retention_days is null (no registered shorter source limit) or integer 1..36500. Unreferenced collector candidates default to 90 days; source content authorization takes precedence even when the item has research references. Unknown legacy provenance is retained conservatively.
- knowledge/research/activity.lifecycle_change(store,kind,id,expected_version,deleted,reason) is the owner-only reversible trash/restore boundary. It preserves versions and marks affected dependencies for review; restore never silently clears review tasks. No implicit cascade.
- knowledge.expire_content(store,id,expected_version,reason,operation_id) clears licensed excerpt/translation/fingerprint in every version using root Store.redact_content, retains version IDs/user notes/metadata and publishes changed availability. This is an explicit, audited exception to immutable payloads, never a rewrite of historical reasoning. Store.compact() must run after commit to truncate WAL and reclaim freed bytes; failures remain visible for retry.
- Deletion coordinator is knowledge.lifecycle: preview explicit versions/dependencies; prepare and verify recovery backup + rights-filtered export; commit only an unchanged plan and explicit confirmation. Reversible user trash is distinct from irreversible source-content expiry. Restore uses the normal trash endpoint.
- Retention routes: GET/PATCH /api/retention; GET /api/retention/preview; POST /api/retention/run. Deletion routes: POST /api/deletions/preview; POST /api/deletions/<plan>/prepare-recovery; POST /api/deletions/<plan>/commit; GET /api/trash; POST /api/trash/<kind>/<id>/restore.
- Initial topic reading_baseline restricts unread (including unscoped changes for the followed scope) without creating fake read_state. Historical windows remain available; a later revised change remains unread even if its first discovery predates the baseline.

## Explicit country background and source selection (2026-09-21)

Topic.country_codes is an optional ISO3-style three-letter array, normalized uppercase. It never derives precise location or country from free-form regions. Topic bundle adds cached observations for explicitly selected countries and permitted source_ids, without rewriting observation ownership or period/version. Citation and export expansion includes the same fixed observation evidence. Empty selection only shows explicitly linked metrics. The topic form exposes source_ids checkboxes; an empty list uses the default enabled free scope defined by M2. Source retention_days is shown as an optional integer field.


## Source policy and current content access (2026-09-21)

M2 atomically publishes `source.policy_changed` only when registered `store/display/export` permissions narrow or a shorter content retention cap is introduced. Payload includes source_id/source_version, old_rights/new_rights, old_retention_days/new_retention_days and reason. M3 `knowledge.on_event` owns finding affected current/historical provenance and marking evidence/claim/event dependencies, then publishes `evidence.updated` with dependency_review for M4/M5. The producer and consumer must ship together; delivery is not acknowledged by an incomplete consumer set.

Read policy intersects requested/current material grants with registered historical source/channel grants and the shortest content deadline. Evidence views retain declared `rights` and add `effective_rights`, `content_policy`, `content_expires_at`; restricted/expired content omits excerpt, translation and fingerprint even before background compaction. User-authored notes and fixed reference identity remain. Ordinary research export includes still-permitted, unexpired content and its expiry; recoverable snapshots have separate anti-revival sanitation rules. A request builds its policy context once inside the Store transaction; no stale global policy cache.

M2 collector `knowledge.ingest(..., origin='collector')` may return a content-omitting receipt containing identity, version, duplicate status and metadata. This is a response boundary, not omission of permitted persisted material. Human writes and read APIs return policy-filtered records. Title similarity is candidate-only: user confirmation updates `origin_evidence_id` and immutable history, never merges events or asserts independent confirmation.

WDI jobs snapshot the explicit topic country selection intersected with configured countries, include it in the scope signature, filter both request and response, and store automatic observations as shared global background. Existing human links are preserved; an empty country selection does not invent a country. Topic background respects selected country/source filters, while fixed research citations remain available independently of the current background view.


## Relevant history projection and recovery policy lineage (2026-09-21)

`Store.policy_snapshots(evidence_ids)` selects every immutable version of each requested Evidence, transitive historical originals, all applicable source/settings/recovery facts, and actual historical incoming citation snapshots (including removed citations and tombstones). Its rebuildable memory index stores facts only. Writes, rollback, same-version licensed-content redaction and external SQLite commits invalidate it. Each read request still builds a new clock-dependent policy context in the same transaction; it never caches permission decisions. Search may count matches in unchanged metadata without serializing every body, but body-only matches and every returned page are sanitized before disclosure. Full snapshot evaluation remains the reference semantics.

M7 owns immutable `recovery_source_policy` facts written during recovery sanitation. Fields: source_id, source_version, source_created_at, rights, retention_days, policy_effective_at, policy_end_at, restored_at, policy_hash, reason. Recovery preserves stricter known source constraints separately from the restored source's native version sequence; matching numeric source versions from different timelines do not overwrite each other. Facts can tighten permissions, never grant them. Source settings and Evidence historical identities remain unchanged.

M2 records internal policy_reviewed_at/policy_reviewed_rights/policy_reviewed_retention_days only on an explicit source PATCH containing rights or retention_days. Caller-supplied internal fields are rejected. A subsequent explicit review defines the boundary for future new materials, without resetting restrictions already applicable to old ones. The Web form omits unchanged policy fields during routine edits, and provides an explicit renewed-review checkbox when the same values should intentionally be reviewed. Source GET adds read-only recovery_constraints with effective end boundaries; Evidence content_policy.recovery_constraints states those relevant to that material. Ordinary notes and fixed references survive.

## Optional GKG metadata adapter (2026-09-21)

`gdelt_gkg` is default-disabled and manually selectable, with config.topic_ids only. `gdelt` remains DOC query + topic_ids. Both share the GDELT provider daily budget and minimum six-second request spacing; index and ZIP each consume a request. No automatic fallback, paid call or implicit historical coverage. GKG strictly validates official HTTPS URLs, sizes, MD5, ZIP member/traversal and decompression bounds; batch metadata is cached atomically across topics/restarts. It matches title/theme keywords and exclusions locally, stores metadata only, leaves published_at unknown, and records batch time separately as provider_seen_at. Every latest-only job retains a historical coverage gap. Source views expose provider budget/usage/minimum interval and a discovery limitation note. Source page distinguishes completed task from complete coverage and displays each job's gap reason.
