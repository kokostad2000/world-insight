"""Isolated real SQLite/backup tests for P0 retention and recovery-first trash."""
import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from server.modules import activity, knowledge, research
from server.modules.knowledge import lifecycle as life
from server.platform.errors import ApiError
from server.platform.store import Store


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world-insight-lifecycle-fixture-')
        self.data = Path(self.tmp.name) / 'data'
        self.data.mkdir()
        (self.data / 'instance.json').write_text(json.dumps({'instance_id': str(uuid.uuid4()), 'format': 1}))
        self.store = Store(self.data / 'world-insight.sqlite')
        self.topic = research.handle(self.store, 'POST', ['topics'], {'question': '隔离生命周期测试，不是真实研究'}, {})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def evidence(self, origin='collector', at='2026-01-01T00:00:00Z', **extra):
        with patch.object(self.store, 'now', return_value=at):
            return knowledge.ingest(self.store, {'title': '隔离候选', 'url': 'https://example.org/' + str(uuid.uuid4()), 'is_fixture': True,
                'topic_id': self.topic['id'], 'rights': {'store': 'excerpt', 'display': 'excerpt', 'export': 'excerpt'}, **extra}, origin=origin)

    def preview(self, *records):
        return life.deletion_preview(self.store, {'targets': [{'kind': kind, 'id': row['id'], 'expected_version': row['version']} for kind, row in records]})

    def confirmation(self, plan):
        return {'confirm': True, 'reason': '隔离测试显式删除', 'plan_hash': plan['plan_hash'], 'recovery_id': plan['recovery']['id'], 'expected_versions': plan['targets']}

    def test_settings_validate_and_require_optimistic_version(self):
        self.assertEqual(life.get_settings(self.store)['candidate_days'], 90)
        row = life.update_settings(self.store, {'expected_version': 0, 'candidate_days': 30})
        self.assertEqual(row['version'], 1)
        with self.assertRaises(ApiError) as conflict:
            life.update_settings(self.store, {'expected_version': 0, 'candidate_days': 40})
        self.assertEqual(conflict.exception.status, 409)
        for body in ({'candidate_days': True}, {'candidate_days': 0}, {'batch_limit': 201}, {'candidate_retention_enabled': 1}):
            with self.assertRaises(ApiError):
                life.update_settings(self.store, {'expected_version': 1, **body})

    def test_retention_boundary_uses_first_collection_not_latest(self):
        row = self.evidence()
        self.store.update('evidence', row['id'], {'collected_at': '2026-04-01T00:00:00Z'}, 1)
        before = life.retention_preview(self.store, '2026-03-31T23:59:59Z')
        due = life.retention_preview(self.store, '2026-04-01T00:00:00Z')
        self.assertEqual(before['actions'], [])
        self.assertEqual(due['actions'][0]['id'], row['id'])
        self.assertTrue(due['actions'][0]['move_to_trash'])

    def test_manual_legacy_notes_reviewed_and_historical_refs_protected(self):
        manual = self.evidence(origin='manual')
        legacy = self.store.create('evidence', {'title': '隔离旧导入', 'status': 'unverified', 'collected_at': '2026-01-01T00:00:00Z'})
        noted = self.evidence(notes='人工笔记')
        reviewed = self.evidence(status='reviewed')
        cited = self.evidence()
        judgment = research.handle(self.store, 'POST', ['judgments'], {'topic_id': self.topic['id'], 'conclusion': '隔离历史引用', 'evidence_version_ids': [cited['id'] + '@1']}, {})
        research.handle(self.store, 'PATCH', ['judgments', judgment['id']], {'expected_version': 1, 'evidence_version_ids': [], 'change_reason': '取消当前引用'}, {})
        result = life.retention_preview(self.store, '2026-09-21T00:00:00Z')
        self.assertEqual(result['actions'], [])
        self.assertEqual({item['id'] for item in result['protected']}, {manual['id'], legacy['id'], noted['id'], reviewed['id'], cited['id']})

    def test_source_expiry_overrides_manual_reference_and_disabled_candidates(self):
        source = self.store.create('source', {'name': '隔离有限授权', 'retention_days': 7})
        evidence = self.evidence(origin='manual', source_id=source['id'], excerpt='restricted-text', translation='译文', notes='保留人工笔记')
        judgment = research.handle(self.store, 'POST', ['judgments'], {'topic_id': self.topic['id'], 'conclusion': '隔离引用', 'evidence_version_ids': [evidence['id'] + '@1']}, {})
        life.update_settings(self.store, {'expected_version': 0, 'candidate_retention_enabled': False})
        with patch.object(self.store, 'now', return_value='2026-01-09T00:00:00Z'):
            result = life.run_retention(self.store, {'operation_id': 'source-7-day'})
        self.assertEqual(result['state'], 'complete')
        self.assertFalse(result['results'][0]['deleted'])
        current = self.store.get('evidence', evidence['id'])
        self.assertEqual(current['notes'], '保留人工笔记')
        self.assertEqual(current['excerpt'], '')
        self.store.drain([research.on_event, activity.on_event])
        self.assertEqual(self.store.get('judgment', judgment['id'])['status'], 'needs_review')
        self.assertEqual(self.store.version(evidence['id'] + '@1')['excerpt'], '')
        self.assertTrue(self.store.integrity()['ok'])

    def test_candidate_run_compacts_bytes_is_bounded_and_idempotent(self):
        marker = 'EXPIRED_CANDIDATE_MARKER_0183' * 200
        first = self.evidence(excerpt=marker, translation=marker)
        self.evidence()
        life.update_settings(self.store, {'expected_version': 0, 'batch_limit': 1})
        with patch.object(self.store, 'now', return_value='2026-09-21T00:00:00Z'):
            result = life.run_retention(self.store, {'operation_id': 'bounded'})
            repeated = life.run_retention(self.store, {'operation_id': 'bounded'})
            rest = life.run_retention(self.store, {'operation_id': 'next'})
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['remaining'], 1)
        self.assertEqual(result, repeated)
        self.assertEqual(len(rest['results']), 1)
        self.assertEqual(len(life.trash(self.store, {})['items']), 2)
        for row in self.store.history('evidence', first['id']):
            self.assertFalse(row['excerpt'])
        for path in self.data.glob('world-insight.sqlite*'):
            self.assertNotIn(marker.encode(), path.read_bytes())

    def test_compaction_failure_stays_visible_and_retry_does_not_redelete(self):
        evidence = self.evidence(excerpt='must disappear')
        with patch.object(self.store, 'compact', side_effect=RuntimeError('busy')):
            result = life.run_retention(self.store, {'operation_id': 'compact-retry'})
        self.assertEqual(result['state'], 'compaction_pending')
        version = self.store.get('evidence', evidence['id'])['version']
        recovered = life.run_retention(self.store, {'operation_id': 'compact-retry'})
        self.assertEqual(recovered['state'], 'complete')
        self.assertEqual(self.store.get('evidence', evidence['id'])['version'], version)

    def test_preview_no_business_mutation_and_includes_historical_path_refs(self):
        evidence = self.evidence()
        path = research.handle(self.store, 'POST', ['impact-paths'], {'topic_id': self.topic['id'], 'title': '隔离路径', 'nodes': [{'id': 'a', 'label': 'A'}, {'id': 'b', 'label': 'B'}], 'edges': [{'from': 'a', 'to': 'b', 'status': 'observed', 'evidence_version_ids': [evidence['id'] + '@1']}]}, {})
        research.handle(self.store, 'PATCH', ['impact-paths', path['id']], {'expected_version': 1, 'edges': [], 'change_reason': '保留旧引用'}, {})
        plan = self.preview(('evidence', evidence))
        self.assertEqual(self.store.get('evidence', evidence['id'])['version'], 1)
        self.assertTrue(any(row['kind'] == 'impact_path' and row['version'] == 1 for row in plan['dependencies']))
        with self.assertRaises(ApiError):
            life.commit_deletion(self.store, plan['id'], {'confirm': True, 'reason': '不准绕过恢复包'})

    def test_verified_backup_export_trash_restore_preserves_history_and_review(self):
        evidence = self.evidence(origin='manual', excerpt='private-original', translation='private-translation', rights={'store': True, 'display': True, 'export': False})
        judgment = research.handle(self.store, 'POST', ['judgments'], {'topic_id': self.topic['id'], 'conclusion': '隔离判断', 'evidence_version_ids': [evidence['id'] + '@1']}, {})
        plan = life.prepare_recovery(self.store, self.preview(('evidence', evidence))['id'])
        exported = json.loads(Path(plan['recovery']['export_path']).read_text())
        self.assertNotIn('private-original', json.dumps(exported))
        self.assertNotIn('private-translation', json.dumps(exported))
        committed = life.commit_deletion(self.store, plan['id'], self.confirmation(plan))
        self.assertEqual(life.commit_deletion(self.store, plan['id'], self.confirmation(plan)), committed)
        self.store.drain([research.on_event, activity.on_event])
        self.assertEqual(self.store.get('judgment', judgment['id'])['status'], 'needs_review')
        self.assertEqual(self.store.all('evidence'), [])
        self.assertEqual(self.store.version(evidence['id'] + '@1')['excerpt'], 'private-original')
        current = self.store.get('evidence', evidence['id'])
        restored = life.restore(self.store, 'evidence', evidence['id'], {'expected_version': current['version'], 'reason': '隔离恢复'})
        self.assertFalse(restored['deleted'])
        self.assertEqual(self.store.get('judgment', judgment['id'])['status'], 'needs_review')
        self.assertTrue(self.store.integrity()['ok'])

    def test_changed_dependency_or_target_rejects_prepared_plan(self):
        evidence = self.evidence(origin='manual')
        plan = life.prepare_recovery(self.store, self.preview(('evidence', evidence))['id'])
        research.handle(self.store, 'POST', ['judgments'], {'topic_id': self.topic['id'], 'conclusion': '备份后新引用', 'evidence_version_ids': [evidence['id'] + '@1']}, {})
        with self.assertRaises(ApiError) as conflict:
            life.commit_deletion(self.store, plan['id'], self.confirmation(plan))
        self.assertEqual(conflict.exception.code, 'plan_changed')
        self.assertFalse(self.store.get('evidence', evidence['id']).get('deleted'))

    def test_corrupt_recovery_or_export_blocks_all_deletion(self):
        for corrupt in ('backup_path', 'export_path'):
            evidence = self.evidence(origin='manual')
            plan = life.prepare_recovery(self.store, self.preview(('evidence', evidence))['id'])
            with Path(plan['recovery'][corrupt]).open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaises(ApiError) as error:
                life.commit_deletion(self.store, plan['id'], self.confirmation(plan))
            self.assertEqual(error.exception.code, 'recovery_invalid')
            self.assertFalse(self.store.get('evidence', evidence['id']).get('deleted'))

    def test_source_permission_change_and_expired_plan_require_new_preview(self):
        source = self.store.create('source', {'name': '隔离来源', 'retention_days': None})
        evidence = self.evidence(origin='manual', source_id=source['id'])
        plan = self.preview(('evidence', evidence))
        self.store.update('source', source['id'], {'retention_days': 2}, 1)
        with self.assertRaises(ApiError) as conflict:
            life.prepare_recovery(self.store, plan['id'])
        self.assertEqual(conflict.exception.code, 'plan_changed')
        plan = self.preview(('evidence', evidence))
        with patch.object(self.store, 'now', return_value='2099-01-01T00:00:00Z'):
            with self.assertRaises(ApiError) as expired:
                life.prepare_recovery(self.store, plan['id'])
        self.assertEqual(expired.exception.code, 'plan_expired')

    def test_multi_target_deletion_is_atomic_on_owner_failure(self):
        first, second = self.evidence(origin='manual'), self.evidence(origin='manual')
        plan = life.prepare_recovery(self.store, self.preview(('evidence', first), ('evidence', second))['id'])
        owner_call = knowledge.lifecycle_change
        count = 0
        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise ApiError(409, 'injected_failure', '隔离故障注入')
            return owner_call(*args, **kwargs)
        with patch.object(knowledge, 'lifecycle_change', side_effect=fail_second):
            with self.assertRaises(ApiError):
                life.commit_deletion(self.store, plan['id'], self.confirmation(plan))
        self.assertEqual(self.store.get('evidence', first['id'])['version'], 1)
        self.assertEqual(self.store.get('evidence', second['id'])['version'], 1)
        self.assertEqual(self.store.get('lifecycle_plan', plan['id'])['state'], 'recovery_ready')

    def test_export_finite_source_omits_body_but_keeps_notes_and_citations(self):
        source = self.store.create('source', {'name': '隔离来源', 'retention_days': 30, 'rights': {'store': True, 'export': True}})
        evidence = self.evidence(origin='manual', source_id=source['id'], excerpt='source-text', notes='user-note')
        exported = life._export(self.store.snapshots(), [{'kind': 'evidence', 'id': evidence['id']}])
        version = exported['snapshots'][0]['record']
        self.assertEqual(version['excerpt'], '')
        self.assertEqual(version['notes'], 'user-note')
        self.assertEqual(version['version'], 1)

    def test_historical_source_cap_and_channel_cap_cannot_be_bypassed(self):
        source = self.store.create('source', {'name': '隔离转载渠道', 'retention_days': 7})
        self.store.update('source', source['id'], {'retention_days': None}, 1)
        evidence = self.evidence(origin='manual', channels=[{'source_id': source['id'], 'url': 'https://example.org/reprint'}])
        result = life.retention_preview(self.store, '2026-01-09T00:00:00Z')
        self.assertEqual(result['actions'][0]['id'], evidence['id'])
        self.assertEqual(result['actions'][0]['action'], 'source_content_expiry')
        self.assertFalse(result['actions'][0]['move_to_trash'])

    def test_restored_candidate_is_manually_protected_without_reviving_body(self):
        evidence = self.evidence(excerpt='expired-text')
        life.run_retention(self.store, {'operation_id': 'before-manual-restore'})
        deleted = self.store.get('evidence', evidence['id'])
        life.restore(self.store, 'evidence', evidence['id'], {'expected_version': deleted['version'], 'reason': '人工决定保留元数据'})
        self.assertEqual(life.retention_preview(self.store)['actions'], [])
        self.assertEqual(self.store.get('evidence', evidence['id'])['excerpt'], '')

    def test_retention_export_omits_due_candidate_even_before_maintenance(self):
        evidence = self.evidence(excerpt='candidate-should-not-export')
        exported = life._export(self.store.snapshots(), [{'kind': 'evidence', 'id': evidence['id']}])
        self.assertNotIn('candidate-should-not-export', json.dumps(exported))
        self.assertEqual(self.store.get('evidence', evidence['id'])['excerpt'], 'candidate-should-not-export')


if __name__ == '__main__':
    unittest.main()
