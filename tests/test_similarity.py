"""Similarity UI seams plus its real domain API; all data are isolated fixtures."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from server.app import Application
from server.platform.config import load_config
from server.platform.errors import ApiError
from server.platform.store import Store

ROOT = Path(__file__).resolve().parents[1]


class SimilarityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world-insight-similarity-test-')
        self.config = load_config(data_dir=self.tmp.name)
        self.store = Store(self.config['db_path'])
        self.app = Application(self.config, self.store, {'instance_id': 'similarity-fixture'})
        self.topic = self.api('topics', {'question': '[夹具] 相似候选检查'})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def api(self, path, body=None, method=None, query=None):
        result = self.app.dispatch(method or ('POST' if body is not None else 'GET'), '/api/' + path, body or {}, query or {})
        self.app.drain()
        return result

    def evidence(self, country, day):
        return self.api('evidence', {'topic_id': self.topic['id'], 'title': f'[夹具] 政策会议 {country} 9月{day}日',
            'url': f'https://example.com/similarity/{country}', 'published_at': f'2026-09-{day}',
            'notes': '[夹具] 人工备注保留', 'is_fixture': True})

    def test_candidate_read_does_not_merge_or_mutate(self):
        first = self.evidence('甲国', '10')
        second = self.evidence('乙国', '12')
        result = self.api('evidence', query={'similar_to': first['id'], 'limit': '10', 'offset': '0'})
        self.assertEqual(result['items'][0]['id'], second['id'])
        self.assertEqual(result['items'][0]['association_status'], 'candidate_only')
        self.assertEqual(self.store.list('evidence')['total'], 2)
        self.assertEqual(self.store.list('event')['total'], 0)
        self.assertEqual(self.store.get('evidence', first['id'])['version'], 1)

    def test_associate_clear_restore_keeps_history_channels_and_fixed_citation(self):
        first = self.evidence('甲国', '10')
        second = self.evidence('乙国', '12')
        judgment = self.api('judgments', {'topic_id': self.topic['id'], 'conclusion': '[夹具] 尚待核验', 'evidence_version_ids': [first['version_id']]})
        for expected, target in ((1, second['id']), (2, None), (3, second['id'])):
            self.api('evidence/' + first['id'], {'expected_version': expected, 'origin_evidence_id': target,
                'change_reason': '[夹具] 明确核对后修改关联'}, 'PATCH')
        history = self.api('evidence/' + first['id'] + '/history')['items']
        self.assertEqual([v['origin_evidence_id'] for v in history], [None, second['id'], None, second['id']])
        self.assertTrue(all(v['notes'] == first['notes'] and v['channels'] == first['channels'] for v in history))
        self.assertEqual(self.store.get('judgment', judgment['id'])['evidence_version_ids'], [first['version_id']])
        self.assertEqual(self.store.list('evidence')['total'], 2)

    def test_cycle_and_stale_version_cannot_overwrite_relationship(self):
        first = self.evidence('甲国', '10')
        second = self.evidence('乙国', '12')
        self.api('evidence/' + first['id'], {'expected_version': 1, 'origin_evidence_id': second['id']}, 'PATCH')
        with self.assertRaises(ApiError) as conflict:
            self.api('evidence/' + first['id'], {'expected_version': 1, 'origin_evidence_id': None}, 'PATCH')
        self.assertEqual(conflict.exception.status, 409)
        with self.assertRaises(ApiError):
            self.api('evidence/' + second['id'], {'expected_version': 1, 'origin_evidence_id': first['id']}, 'PATCH')
        self.assertIsNone(self.store.get('evidence', second['id'])['origin_evidence_id'])

    @unittest.skipUnless(shutil.which('node'), 'Node is only a developer test dependency')
    def test_executable_frontend_behaviors(self):
        result = subprocess.run(['node', '--test', 'tests/similarity_behavior.mjs'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
