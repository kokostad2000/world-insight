"""Isolated real SQLite/archive fixtures for recovery policy lineage; no upstream I/O."""
import contextlib
import http.client
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from ops import backup, runtime
from server.app import Application, handler_class
from server.modules import knowledge, research, sources
from server.modules.knowledge import lifecycle, rights
from server.modules.knowledge.policy_period import RECOVERY_KIND
from server.platform.store import Store

ROOT = Path(__file__).resolve().parents[1]
GRANTED = {'fetch': False, 'store': True, 'display': True, 'export': True, 'ai': False}


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world-insight-policy-restore-fixture-')
        self.base = Path(self.tmp.name)
        self.config = runtime.prepare_config(ROOT, self.base / 'data', 8874)
        self.config['backup_dir'] = self.base / 'backups'
        runtime.atomic_json(self.config['data_dir'] / 'instance.json', {'instance_id': str(uuid.uuid4()), 'format': 1})
        self.store = Store(self.config['db_path'])
        self.opened = [self.store]
        with patch.object(self.store, 'now', return_value=self.day(1)):
            self.source = sources.handle(self.store, 'POST', ['sources'], {'name': '[fixture] restored policy source',
                'adapter': 'manual', 'rights': GRANTED, 'retention_days': None, 'interval_seconds': 600, 'config': {}}, {})
            self.topic = research.handle(self.store, 'POST', ['topics'], {'question': '[fixture] recovery policy lineage'}, {})
        self.row = self.material(self.store, 2, 'OLD_LICENSE_BODY')
        self.ref = self.row['version_id']
        self.judgment = research.handle(self.store, 'POST', ['judgments'], {'topic_id': self.topic['id'],
            'conclusion': '[fixture] preserve authored reference', 'evidence_version_ids': [self.ref]}, {})
        self.package = self.archive(self.store, 2)

    def tearDown(self):
        for store in self.opened:
            store.close()
        self.tmp.cleanup()

    @staticmethod
    def day(day):
        return f'2030-01-{day:02d}T12:00:00Z'

    @contextlib.contextmanager
    def clock(self, day):
        original = lifecycle._time
        with patch.object(backup, 'now', return_value=self.day(day)), patch.object(lifecycle, '_time', side_effect=lambda value=None: original(value or self.day(day))):
            yield

    def material(self, store, day, marker, **extra):
        with patch.object(store, 'now', return_value=self.day(day)):
            return knowledge.ingest(store, {'source_id': self.source['id'], 'title': '[fixture] restored evidence',
                'url': 'https://fixture.example/' + marker, 'excerpt': marker, 'translation': marker + '_TRANSLATION',
                'rights': GRANTED, 'topic_id': self.topic['id'], 'notes': 'USER_NOTE_KEEP', 'is_fixture': True, **extra})

    def archive(self, store, day):
        config = {**self.config, 'data_dir': store.path.parent, 'db_path': store.path}
        with self.clock(day):
            return backup.create_backup(config, output=self.base / (uuid.uuid4().hex + '.wibackup'))['package']

    def shrink(self, cap=7, grants=None):
        with patch.object(self.store, 'now', return_value=self.day(3)):
            self.source = self.store.update('source', self.source['id'], {'retention_days': cap,
                'rights': grants or GRANTED, 'interval_seconds': 900}, self.source['version'])

    def restore(self, day=4, package=None, policy_source=None):
        stage = self.base / ('restored-' + uuid.uuid4().hex)
        with self.clock(day):
            manifest = backup.unpack_verified(package or self.package, stage, policy_source=policy_source or self.store.path)
        store = Store(stage / backup.DB_NAME)
        self.opened.append(store)
        return store, manifest

    def view(self, store, row=None, day=10):
        with patch.object(store, 'now', return_value=self.day(day)):
            return knowledge.handle(store, 'GET', ['evidence', (row or self.row)['id']], {}, {})

    def assert_hidden(self, store, row=None, day=10):
        shown = self.view(store, row, day)
        self.assertEqual(shown['excerpt'], '')
        self.assertEqual(shown['translation'], '')
        self.assertIsNone(shown['content_fingerprint'])
        self.assertTrue(shown['content_policy']['recovery_constraints'])
        return shown

    def test_before_due_restore_persists_cap_then_refetch_patch_and_origin_cannot_show_body(self):
        self.shrink()
        restored, manifest = self.restore()
        self.assertEqual(manifest['restoration_content_policy']['recovery_policy_facts_added'], 1)
        self.assertEqual(restored.get('source', self.source['id'])['retention_days'], None)
        self.assertEqual(restored.get('source', self.source['id'])['interval_seconds'], 600)
        self.assertEqual(len(restored.history('source', self.source['id'])), 1)
        self.assertFalse(restored.get('evidence', self.row['id']).get('content_expired'))
        before = self.view(restored, day=5)
        self.assertFalse(before['content_policy']['content_expired'])
        self.assertEqual(before['content_expires_at'], '2030-01-09T12:00:00.000000Z')
        repeated = self.material(restored, 10, 'OLD_LICENSE_BODY')
        self.assertEqual(repeated['id'], self.row['id'])
        self.assertEqual(restored.get('evidence', repeated['id'])['excerpt'], '')
        self.assertEqual(restored.get('evidence', repeated['id'])['translation'], '')
        self.assert_hidden(restored)
        with patch.object(restored, 'now', return_value=self.day(10)):
            edited = knowledge.handle(restored, 'PATCH', ['evidence', repeated['id']], {'expected_version': repeated['version'],
                'excerpt': 'PATCH_MUST_NOT_SHOW', 'notes': 'USER_NOTE_KEEP', 'change_reason': '[fixture] user correction'}, {})
            self.assertEqual(edited['excerpt'], '')
            self.assertEqual(restored.get('evidence', edited['id'])['excerpt'], '')
            self.assertIsNone(restored.get('evidence', edited['id'])['content_fingerprint'])
        derived = self.material(restored, 10, 'DERIVED_MUST_NOT_SHOW', source_id='manual', origin_evidence_id=self.row['id'])
        self.assertEqual(restored.get('evidence', derived['id'])['excerpt'], '')
        self.assert_hidden(restored, derived)
        with patch.object(restored, 'now', return_value=self.day(10)):
            exported = research.export(restored, {'topic_id': self.topic['id']})
        body = json.dumps(exported)
        self.assertNotIn('PATCH_MUST_NOT_SHOW', body)
        self.assertNotIn('DERIVED_MUST_NOT_SHOW_TRANSLATION', body)
        self.assertEqual(restored.version(self.ref)['notes'], 'USER_NOTE_KEEP')
        self.assertEqual(restored.get('judgment', self.judgment['id'])['evidence_version_ids'], [self.ref])
        with patch.object(restored, 'now', return_value=self.day(10)), self.clock(10):
            lifecycle.run_retention(restored, {'operation_id': 'fixture-restored-policy-cleanup'})
        self.assertTrue(all(row['excerpt'] == '' and row['translation'] == '' for row in restored.history('evidence', self.row['id'])))
        self.assertTrue(restored.integrity()['ok'])

    def test_collector_status_and_name_only_versions_do_not_end_recovery_constraint(self):
        self.shrink()
        restored, _ = self.restore()
        source = restored.get('source', self.source['id'])
        with patch.object(restored, 'now', return_value=self.day(5)):
            source = restored.update('source', source['id'], {'last_success': self.day(5)}, source['version'])
        with patch.object(restored, 'now', return_value=self.day(6)):
            source = sources.handle(restored, 'PATCH', ['sources', source['id']], {'expected_version': source['version'],
                'name': '[fixture] harmless rename'}, {})
        newer = self.material(restored, 7, 'NEW_BUT_STILL_SEVEN_DAYS')
        self.assertEqual(newer['content_policy']['retention_days'], 7)
        self.assertEqual(newer['content_expires_at'], '2030-01-14T12:00:00.000000Z')
        self.assert_hidden(restored, newer, 15)

    def review(self, store, day=11):
        old = store.get('source', self.source['id'])
        with patch.object(store, 'now', return_value=self.day(day)):
            app = Application({**self.config, 'data_dir': store.path.parent, 'db_path': store.path}, store, {'instance_id': 'fixture'})
            result = app.dispatch('PATCH', '/api/sources/' + old['id'], {'expected_version': old['version'],
                'rights': GRANTED, 'retention_days': None}, {})
            self.assertEqual(result['policy_reviewed_at'], self.day(day))
            self.assertEqual(result['policy_reviewed_rights'], GRANTED)
            self.assertIsNone(result['policy_reviewed_retention_days'])
            return result

    def test_same_source_version_reauthorization_allows_new_material_without_old_revival(self):
        self.shrink()
        restored, _ = self.restore()
        fresh_source = self.review(restored)
        self.assertEqual(fresh_source['version'], self.source['version'])  # Two different @2 lineages.
        fresh = self.material(restored, 12, 'FRESH_LEGALLY_REAUTHORIZED')
        self.assertEqual(fresh['excerpt'], 'FRESH_LEGALLY_REAUTHORIZED')
        self.assertEqual(restored.get('evidence', fresh['id'])['excerpt'], 'FRESH_LEGALLY_REAUTHORIZED')
        self.assertIsNone(fresh['content_expires_at'])
        self.assertEqual(fresh['content_policy']['recovery_constraints'], [])
        old = self.material(restored, 12, 'OLD_LICENSE_BODY')
        self.assert_hidden(restored, old, 12)
        self.assertEqual({item['id'] for item in lifecycle.retention_preview(restored, self.day(13))['actions']}, {old['id']})

    def test_recovery_facts_survive_another_backup_and_old_package_restore_with_review_end(self):
        self.shrink()
        restored, _ = self.restore()
        self.review(restored)
        new_package = self.archive(restored, 12)
        copied, manifest = self.restore(13, new_package, restored.path)
        self.assertTrue(copied.all(RECOVERY_KIND))
        self.assert_hidden(copied, day=13)
        # Restoring the original pre-policy package again retains the earlier
        # recovery constraint and its now-known explicit reauthorization end.
        older, _ = self.restore(13, self.package, restored.path)
        self.assert_hidden(older, day=13)
        fresh = self.material(older, 14, 'AFTER_SECOND_RESTORE_REVIEW')
        self.assertEqual(fresh['excerpt'], 'AFTER_SECOND_RESTORE_REVIEW')
        self.assertIsNone(fresh['content_expires_at'])
        before = older.all(RECOVERY_KIND)
        older_path = older.path
        older.close()
        with self.clock(13):
            result = backup.sanitize_snapshot(older_path, policy_source=restored.path)
        older = Store(older_path)
        self.opened.append(older)
        self.assertEqual(result['recovery_policy_facts_added'], 0)
        self.assertEqual(older.all(RECOVERY_KIND), before)
        self.assertTrue(older.integrity()['ok'])

    def test_recovered_rights_restriction_is_explained_and_no_future_cap_is_fabricated(self):
        narrowed = {**GRANTED, 'display': False, 'export': False}
        self.shrink(None, narrowed)
        restored, _ = self.restore()
        shown = self.assert_hidden(restored, day=5)
        self.assertIsNone(shown['content_expires_at'])
        self.assertTrue(any(reason['code'] == 'recovery_source_rights' for reason in shown['content_policy']['reasons']))
        self.review(restored)
        fresh = self.material(restored, 12, 'NEW_RIGHTS_AFTER_REVIEW')
        self.assertEqual(fresh['excerpt'], 'NEW_RIGHTS_AFTER_REVIEW')
        self.assert_hidden(restored, day=12)

    def test_source_current_policy_looser_does_not_erase_historical_applied_limit(self):
        self.shrink()
        with patch.object(self.store, 'now', return_value=self.day(5)):
            self.source = self.store.update('source', self.source['id'], {'retention_days': None}, self.source['version'])
        restored, _ = self.restore(6)
        self.assert_hidden(restored, day=10)
        fresh = self.material(restored, 7, 'NEW_AFTER_EXTERNAL_CAP_ENDED')
        self.assertEqual(fresh['excerpt'], 'NEW_AFTER_EXTERNAL_CAP_ENDED')
        self.assertIsNone(fresh['content_expires_at'])

    def test_unknown_external_policy_time_cannot_hide_an_applied_constraint(self):
        self.shrink()
        with patch.object(self.store, 'now', return_value=self.day(5)):
            self.source = self.store.update('source', self.source['id'], {'retention_days': None}, self.source['version'])
        # Explicitly labelled malformed legacy fixture. Its v2 creation date is
        # inherited from v1 and cannot substitute for a missing policy date.
        legacy = self.store.history('source', self.source['id'])[1]
        legacy.pop('updated_at')
        with self.store.transaction():
            self.store.db.execute("UPDATE versions SET data=? WHERE kind='source' AND id=? AND version=2",
                (json.dumps(legacy), self.source['id']))
        restored, _ = self.restore(6)
        self.assert_hidden(restored, day=10)
        newer = self.material(restored, 12, 'UNKNOWN_POLICY_TIME_IS_CONSERVATIVE')
        self.assertEqual(newer['content_policy']['retention_days'], 7)
        self.assertTrue(all(row['policy_end_at'] is None for row in restored.all(RECOVERY_KIND)))

    def test_collector_versions_of_unchanged_policy_do_not_duplicate_recovery_facts(self):
        self.shrink()
        for index in range(10):
            with patch.object(self.store, 'now', return_value=self.day(4)):
                self.source = self.store.update('source', self.source['id'], {'requests_today': index + 1}, self.source['version'])
        restored, manifest = self.restore(5)
        self.assertEqual(len(restored.all(RECOVERY_KIND)), 1)
        self.assertEqual(manifest['restoration_content_policy']['recovery_policy_facts_added'], 1)
        self.assert_hidden(restored)

    def test_storage_guard_unknown_source_keeps_metadata_and_notes_without_body(self):
        with patch.object(self.store, 'now', return_value=self.day(3)):
            self.store.update('source', self.source['id'], {'rights': None}, self.source['version'])
        row = self.material(self.store, 4, 'UNKNOWN_STORAGE_BODY')
        saved = self.store.get('evidence', row['id'])
        self.assertEqual(saved['title'], '[fixture] restored evidence')
        self.assertEqual(saved['notes'], 'USER_NOTE_KEEP')
        self.assertEqual(saved['excerpt'], '')
        self.assertEqual(saved['translation'], '')
        self.assertIsNone(saved['content_fingerprint'])

    def test_metadata_only_write_after_store_revocation_drops_copied_body(self):
        self.shrink(None, {**GRANTED, 'store': False})
        restored, _ = self.restore()
        # The old unbounded archive precedes revocation. A metadata-only write
        # cannot carry its old body forward into another stored version.
        with patch.object(restored, 'now', return_value=self.day(5)):
            row = knowledge.ingest(restored, {'source_id': self.source['id'], 'title': '[fixture] metadata update',
                'url': self.row['url'], 'rights': GRANTED, 'notes': 'SECOND_USER_NOTE'})
        current = restored.get('evidence', row['id'])
        self.assertEqual(current['excerpt'], '')
        self.assertEqual(current['translation'], '')
        self.assertIsNone(current['content_fingerprint'])
        self.assertIn('USER_NOTE_KEEP', current['notes'])
        self.assertIn('SECOND_USER_NOTE', current['notes'])

    def test_backup_restore_and_new_write_remove_legacy_channel_body_copies(self):
        source = self.source['id']
        legacy = {'source_id': source, 'url': self.row['url'], 'title': 'KEEP_CHANNEL_TITLE', 'notes': 'KEEP_CHANNEL_NOTES',
            'excerpt': 'LEGACY_CHANNEL_BODY_SECRET', 'translation': 'LEGACY_CHANNEL_TRANSLATION_SECRET',
            'content_fingerprint': 'LEGACY_CHANNEL_FINGERPRINT_SECRET'}
        with patch.object(self.store, 'now', return_value=self.day(2)):
            self.store.update('evidence', self.row['id'], {'channels': [legacy]}, self.row['version'])
        package = self.archive(self.store, 2)
        self.shrink()
        restored, _ = self.restore(package=package)
        for row in restored.history('evidence', self.row['id']):
            for channel in row['channels']:
                self.assertFalse(channel.get('excerpt'))
                self.assertFalse(channel.get('translation'))
                self.assertFalse(channel.get('content_fingerprint'))
        preserved = restored.get('evidence', self.row['id'])['channels'][0]
        self.assertEqual(preserved['title'], 'KEEP_CHANNEL_TITLE')
        self.assertEqual(preserved['notes'], 'KEEP_CHANNEL_NOTES')
        for path in restored.path.parent.glob('world-insight.sqlite*'):
            self.assertNotIn(b'LEGACY_CHANNEL_BODY_SECRET', path.read_bytes())
            self.assertNotIn(b'LEGACY_CHANNEL_TRANSLATION_SECRET', path.read_bytes())
            self.assertNotIn(b'LEGACY_CHANNEL_FINGERPRINT_SECRET', path.read_bytes())
        with patch.object(restored, 'now', return_value=self.day(10)):
            current = restored.get('evidence', self.row['id'])
            knowledge.handle(restored, 'PATCH', ['evidence', self.row['id']], {'expected_version': current['version'],
                'channels': [legacy], 'notes': 'USER_NOTE_STILL_SAVED', 'excerpt': 'NEW_FORBIDDEN_BODY'}, {})
        saved = restored.get('evidence', self.row['id'])
        self.assertEqual(saved['excerpt'], '')
        self.assertEqual(saved['notes'], 'USER_NOTE_STILL_SAVED')
        self.assertEqual(saved['channels'][0]['title'], 'KEEP_CHANNEL_TITLE')
        self.assertTrue(all(key not in saved['channels'][0] for key in rights.CONTENT_FIELDS))

    def test_actual_http_expired_write_never_reaches_sqlite_body_fields(self):
        self.shrink()
        restored, _ = self.restore()
        app = Application({**self.config, 'data_dir': restored.path.parent, 'db_path': restored.path}, restored, {'instance_id': 'fixture-http'})
        server = ThreadingHTTPServer(('127.0.0.1', 8874), handler_class(app))
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        try:
            with patch.object(restored, 'now', return_value=self.day(10)):
                connection = http.client.HTTPConnection('127.0.0.1', 8874, timeout=10)
                connection.request('PATCH', '/api/evidence/' + self.row['id'], json.dumps({'expected_version': 1,
                    'excerpt': 'HTTP_INPUT_BODY_MUST_NOT_BE_STORED', 'translation': 'HTTP_INPUT_TRANSLATION_MUST_NOT_BE_STORED',
                    'notes': 'HTTP_USER_NOTE_MUST_SURVIVE'}), {'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:8874'})
                response = connection.getresponse()
                shown = json.loads(response.read())
                connection.close()
                self.assertEqual(response.status, 200, shown)
                self.assertEqual(shown['excerpt'], '')
                self.assertEqual(shown['notes'], 'HTTP_USER_NOTE_MUST_SURVIVE')
            saved = restored.get('evidence', self.row['id'])
            self.assertEqual(saved['excerpt'], '')
            self.assertEqual(saved['translation'], '')
            self.assertIsNone(saved['content_fingerprint'])
            for path in restored.path.parent.glob('world-insight.sqlite*'):
                self.assertNotIn(b'HTTP_INPUT_BODY_MUST_NOT_BE_STORED', path.read_bytes())
                self.assertNotIn(b'HTTP_INPUT_TRANSLATION_MUST_NOT_BE_STORED', path.read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_expired_split_does_not_copy_body_into_either_new_version(self):
        channels = [{'source_id': self.source['id'], 'url': self.row['url']},
            {'source_id': self.source['id'], 'url': 'https://fixture.example/alternate-appearance'}]
        with patch.object(self.store, 'now', return_value=self.day(2)):
            row = knowledge.handle(self.store, 'PATCH', ['evidence', self.row['id']], {'expected_version': self.row['version'], 'channels': channels}, {})
        self.shrink()
        with patch.object(self.store, 'now', return_value=self.day(10)):
            result = knowledge.split(self.store, row['id'], {'expected_version': row['version'],
                'channels': [channels[1]], 'reason': '[fixture] late split after source deadline'})
        for side in ('original', 'split'):
            saved = self.store.get('evidence', result[side]['id'])
            self.assertEqual(saved['excerpt'], '')
            self.assertEqual(saved['translation'], '')
            self.assertIsNone(saved['content_fingerprint'])
            self.assertEqual(saved['notes'], 'USER_NOTE_KEEP')
        self.assertEqual(self.store.get('judgment', self.judgment['id'])['evidence_version_ids'], [self.ref])

    def assert_storage_revoked_restore(self, permission):
        channel = {'source_id': self.source['id'], 'url': self.row['url'], 'title': 'PRESERVE_CHANNEL_TITLE',
            'notes': 'PRESERVE_CHANNEL_NOTE', 'excerpt': 'NO_STORE_CHANNEL_BODY',
            'translation': 'NO_STORE_CHANNEL_TRANSLATION', 'content_fingerprint': 'NO_STORE_CHANNEL_HASH'}
        with patch.object(self.store, 'now', return_value=self.day(2)):
            self.store.update('evidence', self.row['id'], {'channels': [channel], 'excerpt': 'NO_STORE_TOP_BODY',
                'translation': 'NO_STORE_TOP_TRANSLATION'}, self.row['version'])
        legacy_package = self.archive(self.store, 2)
        self.shrink(None, {**GRANTED, 'store': permission})
        restored, manifest = self.restore(package=legacy_package)
        policy = manifest['restoration_content_policy']
        self.assertIn(self.row['id'], policy['storage_restricted_evidence_ids'])
        self.assertEqual(policy['storage_restricted_version_count'], 2)
        for row in restored.history('evidence', self.row['id']):
            self.assertEqual(row['excerpt'], '')
            self.assertEqual(row['translation'], '')
            self.assertIsNone(row['content_fingerprint'])
            self.assertEqual(row['notes'], 'USER_NOTE_KEEP')
            for channel in row.get('channels', []):
                self.assertFalse(channel.get('excerpt'))
                self.assertFalse(channel.get('translation'))
                self.assertFalse(channel.get('content_fingerprint'))
        current_channel = restored.get('evidence', self.row['id'])['channels'][0]
        self.assertEqual(current_channel['title'], 'PRESERVE_CHANNEL_TITLE')
        self.assertEqual(current_channel['notes'], 'PRESERVE_CHANNEL_NOTE')
        self.assertEqual(restored.get('judgment', self.judgment['id'])['evidence_version_ids'], [self.ref])
        for path in restored.path.parent.glob('world-insight.sqlite*'):
            for token in (b'NO_STORE_TOP_BODY', b'NO_STORE_TOP_TRANSLATION', b'NO_STORE_CHANNEL_BODY', b'NO_STORE_CHANNEL_TRANSLATION', b'NO_STORE_CHANNEL_HASH'):
                self.assertNotIn(token, path.read_bytes())
        self.assertTrue(restored.integrity()['ok'])

    def test_restore_revoked_store_false_removes_all_historical_body_copies(self):
        self.assert_storage_revoked_restore(False)

    def test_restore_metadata_only_storage_removes_all_historical_body_copies(self):
        self.assert_storage_revoked_restore('metadata')

    def test_export_restriction_and_trash_do_not_revoke_legal_backup_storage(self):
        with patch.object(self.store, 'now', return_value=self.day(2)):
            updated = self.store.update('evidence', self.row['id'], {'excerpt': 'EXPORT_ONLY_BODY_TOKEN'}, self.row['version'])
        self.shrink(None, {**GRANTED, 'export': False})
        with patch.object(self.store, 'now', return_value=self.day(4)):
            exported = research.export(self.store, {'topic_id': self.topic['id']})
        self.assertNotIn('EXPORT_ONLY_BODY_TOKEN', json.dumps(exported))
        # A legal recovery copy must survive even while its source record is in trash.
        self.store.update('evidence', self.row['id'], {'deleted': True}, updated['version'])
        package = self.archive(self.store, 4)
        restored, manifest = self.restore(5, package)
        self.assertEqual(restored.get('evidence', self.row['id'])['excerpt'], 'EXPORT_ONLY_BODY_TOKEN')
        self.assertEqual(manifest['restoration_content_policy']['storage_restricted_version_count'], 0)


if __name__ == '__main__':
    unittest.main()
