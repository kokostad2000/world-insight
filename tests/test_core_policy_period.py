"""Actual SQLite/backup policy-period fixtures, not provider licence assertions."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ops import backup, runtime
from server.modules import knowledge, research
from server.modules.knowledge import lifecycle, rights
from server.modules.knowledge.policy_period import applicable_source_versions, first_saved_at
from server.platform.store import Store


ROOT = Path(__file__).resolve().parents[1]
GRANTED = {action: True for action in rights.ACTIONS}
DENIED = {action: False for action in rights.ACTIONS}


class SourcePolicyPeriodTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world-insight-policy-period-fixture-')
        self.base = Path(self.tmp.name)
        self.config = runtime.prepare_config(ROOT, self.base / 'data', 8874)
        self.config['backup_dir'] = self.base / 'backups'
        runtime.atomic_json(self.config['data_dir'] / 'instance.json', {'instance_id': str(uuid.uuid4()), 'format': 1})
        self.store = Store(self.config['db_path'])
        self.topic = research.handle(self.store, 'POST', ['topics'], {'question': '[fixture] source policy periods'}, {})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def source(self, day, rights_value=GRANTED, cap=None):
        with patch.object(self.store, 'now', return_value=f'2026-01-{day:02d}T00:00:00Z'):
            return self.store.create('source', {'name': '[fixture] verified policy changes', 'rights': rights_value, 'retention_days': cap})

    def policy(self, source, day, rights_value=GRANTED, cap=None):
        with patch.object(self.store, 'now', return_value=f'2026-01-{day:02d}T00:00:00Z'):
            return self.store.update('source', source['id'], {'rights': rights_value, 'retention_days': cap}, source['version'])

    def material(self, source, day, marker):
        with patch.object(self.store, 'now', return_value=f'2026-01-{day:02d}T12:00:00Z'):
            return knowledge.ingest(self.store, {'source_id': source['id'], 'title': '[fixture] historical permission boundary',
                'url': 'https://fixture.example/' + marker, 'topic_id': self.topic['id'], 'excerpt': marker,
                'notes': 'USER_NOTE_' + marker, 'rights': GRANTED, 'is_fixture': True})

    def assert_backup_body(self, row, expected_body):
        result = backup.create_backup(self.config)
        stage = self.base / ('verified-' + str(uuid.uuid4()))
        backup.unpack_verified(result['package'], stage, policy_source=self.config['db_path'])
        restored = Store(stage / backup.DB_NAME)
        try:
            self.assertEqual(restored.version(row['version_id'])['excerpt'], expected_body)
            self.assertEqual(restored.version(row['version_id'])['notes'], 'USER_NOTE_' + row['url'].rsplit('/', 1)[1])
            self.assertTrue(restored.integrity()['ok'])
        finally:
            restored.close()
        return result

    def test_pre_material_defaults_and_expired_old_cap_do_not_poison_new_legal_content(self):
        source = self.source(1, DENIED, cap=1)
        source = self.policy(source, 2, GRANTED, cap=None)
        row = self.material(source, 3, 'NEW_LEGAL_BODY_AFTER_APPROVAL')
        self.assertEqual(row['excerpt'], 'NEW_LEGAL_BODY_AFTER_APPROVAL')
        self.assertIsNone(row['content_policy']['retention_days'])
        self.assertEqual(lifecycle.retention_preview(self.store, '2026-09-21T00:00:00Z')['actions'], [])
        exported = research.export(self.store, {'topic_id': self.topic['id']})
        self.assertIn('NEW_LEGAL_BODY_AFTER_APPROVAL', json.dumps(exported))
        copied = self.assert_backup_body(row, 'NEW_LEGAL_BODY_AFTER_APPROVAL')
        self.assertEqual(copied['manifest']['content_policy']['omitted_evidence_count'], 0)
        with patch.object(self.store, 'now', return_value='2026-09-21T00:00:00Z'):
            lifecycle.run_retention(self.store, {'operation_id': 'fixture-approved-new-material'})
        self.assertEqual(self.store.get('evidence', row['id'])['excerpt'], 'NEW_LEGAL_BODY_AFTER_APPROVAL')

    def test_policy_that_applied_during_old_material_life_cannot_be_removed_retroactively(self):
        source = self.source(1, GRANTED)
        old = self.material(source, 2, 'OLD_BODY_WITH_APPLIED_LIMIT')
        source = self.policy(source, 3, DENIED, cap=3)
        applied_version = source['version']
        source = self.policy(source, 4, GRANTED, cap=None)
        newer = self.material(source, 5, 'NEW_BODY_AFTER_FRESH_APPROVAL')
        old_view = knowledge.handle(self.store, 'GET', ['evidence', old['id']], {}, {})
        self.assertEqual(old_view['excerpt'], '')
        self.assertEqual(old_view['content_policy']['retention_days'], 3)
        self.assertTrue(any(reason['code'] == 'historical_source_rights' for reason in old_view['content_policy']['reasons']))
        self.assertEqual(knowledge.handle(self.store, 'GET', ['evidence', newer['id']], {}, {})['excerpt'], 'NEW_BODY_AFTER_FRESH_APPROVAL')
        # A delayed outbox delivery must not assign old review obligations to a
        # new material acquired only after that source licence was replaced.
        knowledge.on_event(self.store, {'id': 'fixture-delayed-policy', 'type': 'source.policy_changed', 'aggregate_id': source['id'],
            'payload': {'source_id': source['id'], 'source_version': applied_version, 'reason': '[fixture] delayed restriction'}})
        self.assertTrue(self.store.get('evidence', old['id'])['needs_review'])
        self.assertFalse(self.store.get('evidence', newer['id']).get('needs_review', False))
        preview = lifecycle.retention_preview(self.store, '2026-09-21T00:00:00Z')
        self.assertEqual([item['id'] for item in preview['actions']], [old['id']])
        self.assert_backup_body(old, '')
        self.assert_backup_body(newer, 'NEW_BODY_AFTER_FRESH_APPROVAL')
        with patch.object(self.store, 'now', return_value='2026-09-21T00:00:00Z'):
            lifecycle.run_retention(self.store, {'operation_id': 'fixture-applied-old-limit'})
        self.assertEqual(self.store.version(old['version_id'])['excerpt'], '')
        self.assertEqual(self.store.version(newer['version_id'])['excerpt'], 'NEW_BODY_AFTER_FRESH_APPROVAL')

    def test_preapproval_material_and_unknown_first_save_remain_conservative(self):
        source = self.source(1, DENIED)
        old = self.material(source, 1, 'OLD_UNVERIFIED_LICENCE_FIXTURE')
        source = self.policy(source, 2, GRANTED)
        newer = self.material(source, 3, 'APPROVED_LICENCE_FIXTURE')
        self.assertEqual(knowledge.handle(self.store, 'GET', ['evidence', old['id']], {}, {})['excerpt'], '')
        snapshots = self.store.snapshots()
        for entry in snapshots:
            if entry['kind'] == 'evidence' and entry['record']['id'] == newer['id']:
                entry['record'].pop('created_at', None)
                entry['record'].pop('first_collected_at', None)
        context = rights.build_policy_context(snapshots, now='2026-09-21T00:00:00Z')
        shown = rights.present_evidence(self.store.get('evidence', newer['id']), context)
        self.assertEqual(shown['excerpt'], '')

    def test_modified_collection_time_and_copy_cannot_reset_applied_source_term(self):
        source = self.source(1, GRANTED, cap=3)
        old = self.material(source, 2, 'SOURCE_TERM_CANNOT_RENEW')
        source = self.policy(source, 3, GRANTED, cap=None)
        self.store.update('evidence', old['id'], {'first_collected_at': '2099-01-01T00:00:00Z', 'collected_at': '2099-01-01T00:00:00Z'}, old['version'])
        with patch.object(self.store, 'now', return_value='2026-01-05T12:00:00Z'):
            derived = knowledge.ingest(self.store, {'title': '[fixture] copied provenance', 'origin_evidence_id': old['id'],
                'source_id': 'manual', 'excerpt': 'COPIED_BODY_STILL_BOUNDED', 'rights': GRANTED, 'notes': 'keep copied note'})
        actions = lifecycle.retention_preview(self.store, '2026-09-21T00:00:00Z')['actions']
        self.assertEqual({item['id'] for item in actions}, {old['id'], derived['id']})
        result = backup.create_backup(self.config)
        self.assertEqual(set(result['manifest']['content_policy']['omitted_evidence_ids']), {old['id'], derived['id']})

    def test_unknown_ambiguous_and_nonmonotonic_source_timestamps_keep_restrictions(self):
        first = {'id': 'source', 'version': 1, 'updated_at': '2026-01-01T00:00:00Z', 'rights': DENIED}
        later = {'id': 'source', 'version': 2, 'updated_at': '2026-01-02T00:00:00Z', 'rights': GRANTED}
        self.assertEqual(applicable_source_versions([first, later], '2026-01-03T00:00:00Z'), [later])
        self.assertEqual(applicable_source_versions([first, later], None), [first, later])
        self.assertEqual(applicable_source_versions([first, later], later['updated_at']), [first, later])
        undated = {**later, 'updated_at': None}
        self.assertEqual(applicable_source_versions([first, undated], '2026-01-03T00:00:00Z'), [first, undated])
        backwards = {**later, 'updated_at': '2025-01-01T00:00:00Z'}
        self.assertEqual(applicable_source_versions([first, backwards], '2026-01-03T00:00:00Z'), [first, backwards])
        self.assertIsNone(first_saved_at([{'id': 'e', 'version': 1}, {'id': 'e', 'version': 2, 'created_at': '2026-01-02T00:00:00Z'}]))


if __name__ == '__main__':
    unittest.main()
