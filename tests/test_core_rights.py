"""Isolated real SQLite policy tests; fixtures are not real-source validation."""
import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server.modules import knowledge, research
from server.modules.knowledge import rights
from server.platform.errors import ApiError
from server.platform.store import Store


GRANTED = {action: True for action in rights.ACTIONS}
AT = '2026-01-01T00:00:00Z'
NOW = '2026-09-21T00:00:00Z'


class EvidenceRightsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world-insight-rights-fixture-')
        self.store = Store(Path(self.tmp.name) / 'data' / 'world-insight.sqlite')
        self.source = self.store.create('source', {'name': '[fixture] registered source', 'rights': GRANTED, 'retention_days': None})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def evidence(self, at=AT, origin='manual', **extra):
        with patch.object(self.store, 'now', return_value=at):
            result = knowledge.ingest(self.store, {'title': '[fixture] access policy', 'source_id': self.source['id'],
                'url': 'https://fixture.example/' + str(uuid.uuid4()), 'excerpt': 'LICENSED_BODY_MARKER',
                'translation': 'LICENSED_TRANSLATION_MARKER', 'rights': GRANTED, 'is_fixture': True, **extra}, origin=origin)
        return self.store.get('evidence', result['id'])

    def context(self, now=NOW, **extra):
        return rights.build_policy_context(self.store.snapshots(), now=now, **extra)

    def view(self, row, action='display', now=NOW):
        return rights.present_evidence(row, self.context(now), action)

    def assert_hidden(self, row, action='display', now=NOW):
        shown = self.view(row, action, now)
        self.assertEqual(shown['excerpt'], '')
        self.assertEqual(shown['translation'], '')
        self.assertIsNone(shown['content_fingerprint'])
        self.assertFalse(shown['content_policy']['content_allowed'])
        self.assertTrue(shown['content_restricted'])
        self.assertEqual(shown['version_id'], f'{row["id"]}@{row["version"]}')
        if action == 'export':
            self.assertTrue(shown['export_content_omitted'])
        return shown

    def test_unbounded_granted_content_and_inputs_are_preserved(self):
        row = self.evidence(notes='USER_NOTE_KEEP')
        snapshots = self.store.snapshots()
        originals = copy.deepcopy(snapshots)
        context = rights.build_policy_context(snapshots, now=NOW)
        untouched = copy.deepcopy(context)
        shown = rights.present_evidence(row, context)
        self.assertEqual(shown['excerpt'], row['excerpt'])
        self.assertEqual(shown['translation'], row['translation'])
        self.assertEqual(shown['notes'], 'USER_NOTE_KEEP')
        self.assertEqual(shown['content_fingerprint'], row['content_fingerprint'])
        self.assertTrue(shown['content_policy']['content_allowed'])
        self.assertIsNone(shown['content_expires_at'])
        self.assertEqual(context, untouched)
        self.assertEqual(snapshots, originals)
        shown['notes'] = 'changed returned view'
        self.assertEqual(self.store.get('evidence', row['id']), row)

    def test_source_narrowing_applies_immediately_to_every_version(self):
        old = self.evidence()
        new = self.store.update('evidence', old['id'], {'excerpt': 'LATEST_BODY'}, old['version'])
        self.store.update('source', self.source['id'], {'rights': {**GRANTED, 'display': False}}, 1)
        for row in (old, new):
            shown = self.assert_hidden(row)
            self.assertTrue(any(reason['code'] == 'source_rights' and reason['source_id'] == self.source['id'] for reason in shown['content_policy']['reasons']))
            self.assertEqual(self.view(row, 'export')['excerpt'], row['excerpt'])
        self.assertEqual(self.store.version(old['id'] + '@1')['excerpt'], old['excerpt'])

    def test_source_export_restriction_is_distinct_from_display(self):
        row = self.evidence()
        self.store.update('source', self.source['id'], {'rights': {**GRANTED, 'export': 'metadata'}}, 1)
        self.assertEqual(self.view(row)['excerpt'], row['excerpt'])
        self.assert_hidden(row, 'export')

    def test_registered_metadata_only_source_cannot_be_overridden_by_manual_excerpt(self):
        source = self.store.create('source', {'name': '[fixture] metadata-only official source',
            'rights': {'fetch': True, 'store': 'metadata', 'display': 'metadata', 'export': 'metadata', 'ai': False}}, 'fixture-source-fed')
        row = self.evidence(source_id=source['id'], origin='manual', notes='USER_NOTE_KEEP',
            rights={**GRANTED, 'store': 'excerpt', 'display': 'excerpt', 'export': 'excerpt'})
        for action in ('display', 'export'):
            shown = self.assert_hidden(row, action)
            self.assertEqual(shown['notes'], 'USER_NOTE_KEEP')
            self.assertEqual(shown['effective_rights']['store'], 'metadata')

    def test_additional_current_source_policy_is_applied_without_mutating_snapshots(self):
        row = self.evidence()
        snapshots = self.store.snapshots()
        stricter = {**self.source, 'version': 2, 'rights': {**GRANTED, 'export': False}}
        context = rights.build_policy_context(snapshots, sources=[stricter], now=NOW)
        shown = rights.present_evidence(row, context, 'export')
        self.assertFalse(shown['content_policy']['content_allowed'])
        self.assertEqual(shown['excerpt'], '')
        self.assertEqual(self.store.get('source', self.source['id'])['version'], 1)

    def test_historical_stricter_source_policy_explains_no_resurrection(self):
        row = self.evidence()
        source = self.store.update('source', self.source['id'], {'rights': {**GRANTED, 'export': 'metadata'}}, 1)
        self.store.update('source', source['id'], {'rights': GRANTED}, source['version'])
        shown = self.assert_hidden(row, 'export')
        reasons = shown['content_policy']['reasons']
        self.assertTrue(any(reason['code'] == 'historical_source_rights' and reason['version'] == 2 and reason['action'] == 'export' for reason in reasons))

    def test_removed_historical_channel_and_old_source_still_constrain_access(self):
        constrained = self.store.create('source', {'name': '[fixture] old channel', 'rights': {**GRANTED, 'export': False}, 'retention_days': 7})
        row = self.evidence(channels=[{'source_id': constrained['id'], 'url': 'https://fixture.example/channel'}])
        current = self.store.update('evidence', row['id'], {'channels': [], 'source_id': 'manual'}, 1)
        for version in (row, current):
            shown = self.assert_hidden(version, 'export', '2026-01-02T00:00:00Z')
            self.assertIn(constrained['id'], shown['content_policy']['source_ids'])
            self.assertEqual(shown['content_policy']['retention_days'], 7)
            self.assert_hidden(version, 'display', '2026-01-08T00:00:00Z')

    def test_source_deadline_uses_first_collection_and_shortest_historical_term(self):
        source = self.store.update('source', self.source['id'], {'retention_days': 7}, 1)
        row = self.evidence(notes='USER_NOTE_KEEP')
        current = self.store.update('evidence', row['id'], {'collected_at': '2026-07-01T00:00:00Z'}, 1)
        self.store.update('source', source['id'], {'retention_days': 30}, source['version'])
        before = self.view(current, now='2026-01-07T23:59:59Z')
        self.assertEqual(before['excerpt'], row['excerpt'])
        for version in (row, current):
            shown = self.assert_hidden(version, now='2026-01-08T00:00:00Z')
            self.assertTrue(shown['content_expired'])
            self.assertEqual(shown['content_expires_at'], '2026-01-08T00:00:00.000000Z')
            self.assertEqual(shown['notes'], 'USER_NOTE_KEEP')

    def test_future_source_deadline_is_included_in_legal_ordinary_export(self):
        self.store.update('source', self.source['id'], {'retention_days': 7}, 1)
        row = self.evidence(notes='USER_NOTE_KEEP')
        shown = self.view(row, 'export', '2026-01-02T00:00:00Z')
        self.assertEqual(shown['excerpt'], row['excerpt'])
        self.assertEqual(shown['translation'], row['translation'])
        self.assertTrue(shown['content_policy']['content_allowed'])
        self.assertFalse(shown['content_policy']['content_expired'])
        self.assertEqual(shown['content_expires_at'], '2026-01-08T00:00:00.000000Z')

    def test_due_untouched_collector_is_hidden_before_physical_cleanup(self):
        old = self.evidence(origin='collector')
        current = self.store.update('evidence', old['id'], {'collected_at': '2026-09-20T00:00:00Z'}, 1)
        for version in (old, current):
            shown = self.assert_hidden(version)
            self.assertTrue(any(reason['code'] == 'candidate_expiry' for reason in shown['content_policy']['reasons']))
            self.assertEqual(shown['content_expires_at'], '2026-04-01T00:00:00.000000Z')
        self.assertEqual(self.store.get('evidence', old['id'])['excerpt'], old['excerpt'])

    def test_historical_user_notes_and_research_references_protect_unbounded_candidate(self):
        noted = self.evidence(origin='collector', notes='HISTORICAL_USER_NOTE')
        current = self.store.update('evidence', noted['id'], {'notes': '', 'manually_touched': False}, 1)
        for row in (noted, current):
            self.assertEqual(self.view(row)['excerpt'], row['excerpt'])
        cited = self.evidence(origin='collector')
        topic = research.handle(self.store, 'POST', ['topics'], {'question': '[fixture] historical citation'}, {})
        judgment = research.handle(self.store, 'POST', ['judgments'], {'topic_id': topic['id'], 'conclusion': '[fixture] remains referenced', 'evidence_version_ids': [cited['id'] + '@1']}, {})
        research.handle(self.store, 'PATCH', ['judgments', judgment['id']], {'expected_version': 1, 'evidence_version_ids': [], 'change_reason': '[fixture] preserve historical citation'}, {})
        self.assertEqual(self.view(cited, 'export')['excerpt'], cited['excerpt'])

    def test_missing_unknown_and_invalid_rights_never_grant_body(self):
        for permission in (None, False, 'unknown', 'metadata', 'link_only', 1, ['full']):
            with self.subTest(permission=permission):
                row = self.evidence()
                bad = self.store.update('evidence', row['id'], {'rights': {'store': True, 'display': permission}}, 1)
                self.assert_hidden(bad)
                self.assert_hidden(row)
        source = self.store.create('source', {'name': '[fixture] unregistered licence'})
        self.assert_hidden(self.evidence(source_id=source['id']))

    def test_builtin_manual_alias_requires_explicit_rights_but_no_registry_entry(self):
        row = self.evidence(source_id='manual', notes='USER_NOTE_KEEP')
        self.assertEqual(self.view(row)['excerpt'], row['excerpt'])
        current = self.store.update('evidence', row['id'], {'rights': {}}, 1)
        self.assert_hidden(current)

    def test_unknown_source_or_url_only_channel_fails_closed(self):
        row = self.evidence()
        bad_source = self.store.update('evidence', row['id'], {'source_id': 'fixture-missing-source'}, 1)
        self.assert_hidden(bad_source)
        other = self.evidence(channels=['https://fixture.example/unregistered'])
        self.assert_hidden(other)

    def test_store_grant_and_full_body_scope_are_both_enforced(self):
        row = self.evidence(content_scope='full')
        self.store.update('source', self.source['id'], {'rights': {**GRANTED, 'display': 'excerpt'}}, 1)
        self.assert_hidden(row)
        self.assertEqual(self.view(row, 'export')['excerpt'], row['excerpt'])
        current = self.store.update('evidence', row['id'], {'rights': {**GRANTED, 'store': 'metadata'}}, 1)
        self.assert_hidden(current, 'export')

    def test_evidence_snapshot_and_current_grants_intersect(self):
        old = self.evidence(rights={**GRANTED, 'export': False})
        new = self.store.update('evidence', old['id'], {'rights': GRANTED}, 1)
        self.assert_hidden(old, 'export')
        self.assertEqual(self.view(new, 'export')['excerpt'], new['excerpt'])

    def test_expiry_marker_survives_newer_attempt_to_clear_it(self):
        row = self.evidence(notes='USER_NOTE_KEEP')
        expired = self.store.update('evidence', row['id'], {'content_expired': True}, 1)
        current = self.store.update('evidence', row['id'], {'content_expired': False}, expired['version'])
        for version in (row, expired, current):
            shown = self.assert_hidden(version)
            self.assertEqual(shown['notes'], 'USER_NOTE_KEEP')

    def test_trash_hides_body_without_removing_authored_notes_or_references(self):
        row = self.evidence(notes='USER_NOTE_KEEP')
        current = self.store.update('evidence', row['id'], {'deleted': True, 'evidence_version_ids': ['fixture-ref@1']}, 1)
        shown = self.assert_hidden(current, 'export')
        self.assertEqual(shown['notes'], 'USER_NOTE_KEEP')
        self.assertEqual(shown['evidence_version_ids'], ['fixture-ref@1'])
        self.assert_hidden(row)

    def test_transitive_original_provenance_cannot_reset_source_deadline(self):
        limited = self.store.create('source', {'name': '[fixture] original provider', 'rights': GRANTED, 'retention_days': 7})
        original = self.evidence(source_id=limited['id'])
        intermediary = self.evidence(at='2026-01-05T00:00:00Z', origin_evidence_id=original['id'])
        last = self.evidence(at='2026-01-07T00:00:00Z', origin_evidence_id=intermediary['id'])
        detached = self.store.update('evidence', last['id'], {'origin_evidence_id': None}, 1)
        self.assert_hidden(detached, now='2026-01-08T00:00:00Z')

    def test_incomplete_context_and_invalid_source_term_do_not_leak(self):
        row = self.evidence()
        context = self.context()
        newer = self.store.update('evidence', row['id'], {'excerpt': 'NEW_CONTENT'}, 1)
        result = rights.present_evidence(newer, context)
        self.assertFalse(result['content_policy']['content_allowed'])
        self.assertEqual(result['excerpt'], '')
        self.store.update('source', self.source['id'], {'retention_days': 'seven'}, 1)
        with self.assertRaises(ApiError) as error:
            self.context()
        self.assertEqual(error.exception.code, 'invalid_source_retention')

    def test_finite_term_without_known_start_fails_closed(self):
        row = self.evidence()
        snapshots = self.store.snapshots()
        for entry in snapshots:
            if entry['kind'] == 'source':
                entry['record']['retention_days'] = 7
            elif entry['kind'] == 'evidence':
                for field in ('created_at', 'collected_at', 'first_collected_at'):
                    entry['record'][field] = None
        context = rights.build_policy_context(snapshots, now=NOW)
        shown = rights.present_evidence(row, context)
        self.assertEqual(shown['excerpt'], '')
        self.assertTrue(any(reason['code'] == 'unknown_retention_start' for reason in shown['content_policy']['reasons']))

    def test_context_is_built_once_for_many_versions_and_never_contains_body(self):
        row = self.evidence()
        for _ in range(8):
            row = self.store.update('evidence', row['id'], {'notes': '[fixture] editable user note'}, row['version'])
        from server.modules.knowledge import lifecycle
        with patch.object(rights, 'evaluate_retention', wraps=lifecycle.evaluate_retention) as evaluator:
            context = self.context()
            for version in self.store.history('evidence', row['id']):
                rights.present_evidence(version, context)
            self.assertEqual(evaluator.call_count, 1)
        self.assertNotIn('LICENSED_BODY_MARKER', repr(context))
        self.assertNotIn('editable user note', repr(context))


if __name__ == '__main__':
    unittest.main()
