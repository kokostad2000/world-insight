# Core domain first integration handoff

2026-09-20; branch `dev/core`; worktree `.worktrees/core`.

## Changed paths and ownership

- `server/modules/knowledge/__init__.py`: M3 evidence/claim/event/metric domain, acquisition boundary and corrections.
- `server/modules/knowledge/validation.py`: pure domain input validation; no persistence.
- `server/modules/research/__init__.py`: M4 topic/judgment/scenario/path/review, bundle/export and correction consumer.
- `tests/test_core_domain.py`: 20 isolated SQLite fixture scenarios.
- This handoff only. No shared-contract/platform/app/dependency modifications by core owner.

## API details

All standard v1 routes are implemented; PATCH requires expected_version and research revisions require change_reason. Historical versions cannot be edited/deleted. Topic pause/resume/archive uses status PATCH.

- `knowledge.ingest(store,data)` returns evidence with `version_id`. Canonical URL/source record/content fingerprint exact matching retains channels. Similar titles only return candidates via `GET evidence?similar_to=<id>`.
- Evidence `topic_ids` retains all associated topics; PATCH topic_ids removes associations without deleting material/history and adjusts primary topic_id. Root-approved extension.
- `knowledge.upsert_observation(store,data)` preserves identity `(source_id,indicator,country_code,period)` and versioned revisions. `provider_seen_at` remains separate from published_at.
- Evidence channels accept objects `{source_id,url,source_record_id?,publisher?,title?}` or URL strings. Evidence detail includes relations/source_counts. Collections count the returned page when using the default fast pagination path.
- Default rights allow metadata only; nonempty excerpt requires explicit store permission. rights accepts boolean or metadata/link_only/excerpt/full/allowed. Display/export filter current and historical evidence against current restrictions.
- Corrections require reason/expected_version/substantive; corrected/withdrawn requires substantive=true. Inaccessible/restricted still propagate dependency review without representing a fact retraction. Source formatting updates remain candidates. Split preserves records and emits dependency review.
- Topic bundle contains topic,evidence,claims,events,judgments,scenarios,impact_paths,reviews,observations,citations,source_counts,sources,review_summary,unknowns. No current material is substituted for a historical citation.
- JSON export returns bundle plus histories/generated_at/boundaries; Markdown returns `{filename,format,content,generated_at}`. Source metadata is allowlisted; credentials are excluded.
- Impact nodes `{id,label,note?}`, edges `{from,to,status,evidence_version_ids,note?,needs_review?}`. Reviewed scenarios need expiry, assumptions, signals, invalidation criteria, review date, reviewer; no opposition is valid when counterevidence_search explains the search.
- Assumption-only judgments retain evidence_support/support_label after review and export. Predictions require expiry/outcome criteria.
- Root-approved `review.next_review_date` optional: a current-version review writes last_reviewed_version/last_review_id to a new judgment version and clears/reschedules review_date. Historical-version review does not clear current due dates. `needs_review` remains until explicit judgment re-review.
- `research.on_event` uses review_event_ids and stable outbox event ids. Retry does not repeat versions/notifications. Root must atomically deliver research then activity; history is untouched.

## Actually executed

`python3 -m unittest tests.test_core_domain tests.test_platform -v` — 25 passed, 0.087 seconds (20 core + 5 platform). Python 3.11 / actual SQLite databases in TemporaryDirectory; fixtures explicitly labeled; no network or ports used. Compileall also passed.

Core behavior coverage: persisted create/edit/reopen/export, stale-window 409, canonical duplicate channels and topic unlink, idempotent ingest, similar titles and unknown event time, separate conflicting claims, format-only updates, retraction dependency propagation/retry/old versions, non-substantive retraction rejection, country precision, yearly/null metrics/revisions, same URL separate source records, assumption-only reviewed labels, honest missing opposition, indeterminate reviews, split/re-ingest, ten reports/one chain, export credential/rights filtering, inaccessible/restricted propagation and historical redaction, current versus old version review due handling. Test bodies are authoritative evidence; this is domain verification, not browser/live-source/Mac ops acceptance.

## Unverified and remaining integration work

- Browser flows and root activity integration have not run in this worktree. Root to execute after merge.
- No real source access or official material research performed here; no seven-day observation.
- 20k material/5k event performance not measured. Main URL/fingerprint/source_record_id dedup uses indexed Store.find; alternate merged channel identities need a future persistent alias index to guarantee dedup when a subsequent fetch omits the content fingerprint. This is an explicit remaining AC-02/03 robustness item, not claimed complete.
- Source-chain count currently uses directly registered origin ids, not arbitrary-depth ancestor collapse; root should validate/complete transitive chain reporting.
- Explicit dependency references only. Paths and claims/events are marked, research references concrete evidence versions; unregistered semantic dependencies are not inferred.
- M7 backups/restores/updates and real Mac acceptance belong to next implementation round.

## Merge order

1. Root platform commit 762b89a (already merged into dev/core).
2. This core commit (domain code/tests/handoff only).
3. Integrate activity, web and sources; exercise HTTP/browser correction, due dates, version conflicts and persistence before broad acceptance claims.
