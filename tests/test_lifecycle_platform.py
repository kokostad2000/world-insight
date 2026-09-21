"""P0 retention foundations: real SQLite bytes, provenance and reference safety."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.modules import activity, knowledge, research
from server.platform.errors import ApiError
from server.platform.store import Store


class LifecyclePlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'world-insight.sqlite')
        self.topic = research.handle(self.store, 'POST', ['topics'], {'question': '隔离生命周期验收'}, {})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def evidence(self, **extra):
        return knowledge.ingest(self.store, {'title': '隔离材料', 'url': 'https://example.org/fixture',
            'topic_id': self.topic['id'], 'rights': {'store': 'excerpt', 'display': 'excerpt', 'export': 'excerpt'}, **extra}, origin='collector')

    def test_duplicate_registration_keeps_note_and_first_collection(self):
        original = self.evidence()
        self.assertEqual(original['ingest_origin'], 'collector')
        self.assertFalse(original['manually_touched'])
        duplicate = knowledge.ingest(self.store, {'title': original['title'], 'url': original['url'],
            'notes': '人工核对了原始链接；并非全文核查', 'material_type': 'statement'})
        self.assertTrue(duplicate['manually_touched'])
        self.assertIn('人工核对', duplicate['notes'])
        self.assertEqual(duplicate['first_collected_at'], original['first_collected_at'])
        self.assertEqual(duplicate['material_type'], 'statement')
        again = self.evidence()
        self.assertEqual(again['notes'], duplicate['notes'])
        self.assertEqual(again['first_collected_at'], original['first_collected_at'])

    def test_content_expiry_removes_all_versions_and_sqlite_bytes(self):
        marker = 'LICENSED_CONTENT_SENTINEL_81b7f5a' * 100
        first = self.evidence(excerpt=marker, translation=marker)
        second = knowledge.handle(self.store, 'PATCH', ['evidence', first['id']],
            {'notes': '我的笔记保留', 'expected_version': first['version']}, {})
        expired = knowledge.expire_content(self.store, first['id'], second['version'], '来源许可到期', 'expire-1')
        self.store.compact()
        for version in self.store.history('evidence', first['id']):
            self.assertEqual(version['excerpt'], '')
            self.assertEqual(version['translation'], '')
        self.assertEqual(self.store.version(first['id']+'@1')['id'], first['id'])
        self.assertEqual(expired['notes'], '我的笔记保留')
        for path in Path(self.tmp.name).glob('world-insight.sqlite*'):
            self.assertNotIn(marker.encode(), path.read_bytes())
        self.assertTrue(self.store.integrity()['ok'])
        self.assertEqual(knowledge.expire_content(self.store, first['id'], second['version'], '来源许可到期', 'expire-1')['version'], expired['version'])
        reingested = self.evidence(excerpt=marker)
        self.assertEqual(reingested['excerpt'], '')

    def test_expiry_erases_legacy_channel_body_from_every_version_and_disk(self):
        marker = 'LEGACY_CHANNEL_LICENSE_BODY_9381' * 100
        first = self.evidence()
        legacy = self.store.update('evidence', first['id'], {'channels': [
            {'url': 'https://example.org/legacy', 'source_id': 'manual', 'title': '原始渠道标题',
             'excerpt': marker, 'translation': marker, 'content_fingerprint': marker,
             'notes': '渠道人工备注保留'}]}, first['version'])
        self.store.policy_snapshots([first['id']])
        knowledge.expire_content(self.store, first['id'], legacy['version'], '明确许可到期', 'expire-legacy-channel')
        self.store.compact()
        for version in self.store.history('evidence', first['id']):
            for channel in version.get('channels', []):
                self.assertNotIn(marker, str(channel))
                if channel.get('url') == 'https://example.org/legacy':
                    self.assertEqual(channel['notes'], '渠道人工备注保留')
                    self.assertEqual(channel['title'], '原始渠道标题')
        for path in Path(self.tmp.name).glob('world-insight.sqlite*'):
            self.assertNotIn(marker.encode(), path.read_bytes())
        self.assertNotIn(marker, str(self.store.policy_snapshots([first['id']])))

    def test_trash_keeps_old_reference_blocks_new_and_restore_keeps_review(self):
        evidence = self.evidence()
        ref = evidence['id']+'@1'
        judgment = research.handle(self.store, 'POST', ['judgments'], {'topic_id': self.topic['id'],
            'conclusion': '隔离判断', 'evidence_version_ids': [ref]}, {})
        deleted = knowledge.lifecycle_change(self.store, 'evidence', evidence['id'], 1, True, '显式测试删除')
        self.store.drain([research.on_event, activity.on_event])
        self.assertEqual(self.store.all('evidence'), [])
        self.assertEqual(self.store.list('evidence')['total'], 0)
        self.assertEqual(len(self.store.all('evidence', include_deleted=True)), 1)
        self.assertEqual(self.store.get('judgment', judgment['id'])['status'], 'needs_review')
        with self.assertRaises(ApiError):
            knowledge.handle(self.store, 'POST', ['claims'], {'subject': '主体', 'statement': '新引用应拒绝', 'evidence_version_ids': [ref]}, {})
        self.assertEqual(self.evidence()['suppressed'], 'deleted')
        knowledge.lifecycle_change(self.store, 'evidence', evidence['id'], deleted['version'], False, '测试恢复')
        self.assertEqual(self.store.get('judgment', judgment['id'])['status'], 'needs_review')
        self.assertEqual(self.store.version(ref)['title'], evidence['title'])

    def test_manual_duplicate_cannot_bypass_correction_propagation(self):
        evidence = self.evidence()
        with self.assertRaises(ApiError) as error:
            knowledge.ingest(self.store, {'title': evidence['title'], 'url': evidence['url'], 'status': 'withdrawn'})
        self.assertEqual(error.exception.code, 'correction_required')

    def test_topic_country_background_reuses_observation_without_rewriting_identity(self):
        from server.modules import sources
        sources.seed_sources(self.store)
        source_id = next(s['id'] for s in self.store.all('source') if s['adapter'] == 'world_bank')
        evidence = self.evidence(source_id=source_id)
        observation = knowledge.upsert_observation(self.store, {'indicator': 'NY.GDP.MKTP.CD', 'country_code': 'USA',
            'value': None, 'unit': 'USD', 'period': '2025', 'source_id': source_id, 'evidence_version_ids': [evidence['id']+'@1']})
        self.assertEqual(research.bundle(self.store, self.topic['id'])['observations'], [])
        topic = research.handle(self.store, 'PATCH', ['topics', self.topic['id']],
            {'country_codes': ['usa'], 'expected_version': 1}, {})
        result = research.bundle(self.store, topic['id'])
        self.assertEqual([r['id'] for r in result['observations']], [observation['id']])
        self.assertIsNone(result['observations'][0]['value'])
        self.assertEqual(result['observations'][0]['period'], '2025')
        self.assertEqual(self.store.get('observation', observation['id'])['version'], 1)
        self.assertIsNone(self.store.get('observation', observation['id'])['topic_id'])
        self.assertTrue(any(row['id'] == evidence['id'] for row in result['citations']))
        research.handle(self.store, 'PATCH', ['topics', topic['id']],
            {'source_ids': ['source-fed'], 'expected_version': topic['version']}, {})
        self.assertEqual(research.bundle(self.store, topic['id'])['observations'], [])

    def test_reading_baseline_limits_unread_without_faking_read_history(self):
        baseline = '2026-09-20T00:00:00Z'
        self.store.update('topic', self.topic['id'], {'reading_baseline': baseline}, 1)
        with patch.object(self.store, 'now', return_value='2026-08-01T00:00:00Z'):
            old = self.store.create('change', {'topic_id': self.topic['id'], 'topic_ids': [self.topic['id']],
                'title': '旧变化', 'discovered_at': '2026-08-01T00:00:00Z'})
            self.store.create('change', {'title': '旧全局来源失败', 'discovered_at': '2026-08-01T00:00:00Z'})
        with patch.object(self.store, 'now', return_value='2026-09-21T00:00:00Z'):
            self.assertEqual(activity.dashboard(self.store, {'window': 'unread'})['total'], 0)
            history = activity.dashboard(self.store, {'window': 'custom', 'since': '2026-07-01T00:00:00Z'})
            self.assertEqual(history['total'], 2)
            self.assertTrue(all(not row['read'] and row['before_reading_baseline'] for row in history['items']))
            self.store.update('change', old['id'], {'detail': '基线后有新更正'}, 1)
            self.assertEqual(activity.dashboard(self.store, {'window': 'unread'})['total'], 1)
            self.assertEqual(self.store.all('read_state'), [])


if __name__ == '__main__':
    unittest.main()
