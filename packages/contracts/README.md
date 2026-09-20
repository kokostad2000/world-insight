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

`evidence.created`, `evidence.updated`, `evidence.corrected`, `event.created`, `claim.created`, `judgment.created`, `judgment.revised`, `research.needs_review`, `source.failed`, `source.recovered`. Payload includes topic_id, object/version ids, title, reason; evidence corrected includes evidence_id and old_version_ids. Root consumers always research then activity. A failure rolls back delivery side effects and remains retryable. Historical judgment snapshots are never rewritten by current review flags.
