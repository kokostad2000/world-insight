"""Targeted permission histories must equal full-history decisions after real writes."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.modules.knowledge import policy_context
from server.modules.knowledge.rights import build_policy_context, effective_policy, present_evidence
from server.modules import sources, knowledge
from server.platform.store import Store


RIGHTS = {'fetch': True, 'store': True, 'display': True, 'export': True, 'ai': False}
NOW = '2026-09-21T00:00:00Z'


class PolicyProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world-insight-policy-projection-fixture-')
        self.store = Store(Path(self.tmp.name) / 'data.sqlite')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def evidence(self, name, **extra):
        return self.store.create('evidence', {'title': '[fixture] ' + name, 'source_id': 'manual',
            'rights': RIGHTS, 'channels': [], 'excerpt': '[fixture] content', 'notes': '',
            'status': 'unverified', 'content_scope': 'excerpt', 'ingest_origin': 'collector',
            'first_collected_at': '2026-01-01T00:00:00Z', 'collected_at': '2026-01-01T00:00:00Z',
            **extra}, name)

    def compare(self, record):
        with self.store.transaction():
            full = build_policy_context(self.store.snapshots(), now=NOW)
            selected = build_policy_context(self.store.policy_snapshots([record['id']]), now=NOW)
            self.assertEqual(effective_policy(record, full), effective_policy(record, selected))
            self.assertEqual(present_evidence(record, full), present_evidence(record, selected))
            return selected

    def test_old_nested_citation_removed_later_still_protects_collector(self):
        row = self.evidence('protected')
        self.store.create('impact_path', {'edges': [{'evidence_version_ids': ['protected@1']}]}, 'path')
        self.store.update('impact_path', 'path', {'edges': []}, 1)
        for i in range(80):
            self.evidence('unrelated-' + str(i))
        context = self.compare(row)
        self.assertIsNone(context['evidence']['protected']['due'])
        selected = self.store.policy_snapshots(['protected'])
        self.assertEqual({x['record']['id'] for x in selected if x['kind'] == 'evidence'}, {'protected'})
        self.assertTrue(present_evidence(row, context)['excerpt'])

    def test_historical_original_links_and_removed_channels_keep_policy(self):
        source = self.store.create('source', {'rights': RIGHTS, 'retention_days': None}, 'licence')
        original = self.evidence('original', source_id='licence', ingest_origin='manual')
        child = self.evidence('child', origin_evidence_id=original['id'], ingest_origin='manual')
        child = self.store.update('evidence', child['id'], {'origin_evidence_id': None}, 1)
        self.store.update('source', source['id'], {'rights': {**RIGHTS, 'display': False}}, 1)
        context = self.compare(child)
        self.assertEqual(set(context['evidence']), {'child', 'original'})
        self.assertEqual(present_evidence(child, context)['excerpt'], '')

    def test_failed_transaction_cannot_reuse_uncommitted_permission_index(self):
        row = self.evidence('rollback', ingest_origin='manual')
        self.compare(row)
        with self.assertRaisesRegex(RuntimeError, 'rollback fixture'):
            with self.store.transaction():
                changed = self.store.update('evidence', row['id'], {'rights': {**RIGHTS, 'display': False}}, 1)
                self.assertFalse(present_evidence(changed, self.compare(changed))['excerpt'])
                raise RuntimeError('rollback fixture')
        self.assertTrue(present_evidence(row, self.compare(row))['excerpt'])

    def test_external_connection_commit_and_redaction_invalidate_fact_index(self):
        row = self.evidence('external', ingest_origin='manual')
        self.compare(row)
        other = Store(self.store.path)
        try:
            changed = other.update('evidence', row['id'], {'rights': {**RIGHTS, 'display': False}}, 1)
        finally:
            other.close()
        self.assertFalse(present_evidence(changed, self.compare(changed))['excerpt'])
        redacted = self.store.redact_content('evidence', row['id'], 2, 'fixture expiry', 'fixture-operation')
        selected = self.store.policy_snapshots([row['id']])
        self.assertTrue(all(not entry['record']['excerpt'] for entry in selected if entry['kind'] == 'evidence'))
        self.assertTrue(present_evidence(redacted, self.compare(redacted))['content_expired'])

    def test_same_fact_index_reevaluates_time_at_exact_candidate_deadline(self):
        row = self.evidence('deadline', first_collected_at='2026-06-23T00:00:00Z', collected_at='2026-06-23T00:00:00Z')
        with patch.object(self.store, 'now', return_value='2026-09-20T23:59:59Z'):
            self.assertTrue(present_evidence(row, policy_context(self.store, [row['id']]))['excerpt'])
        with patch.object(self.store, 'now', return_value=NOW):
            self.assertFalse(present_evidence(row, policy_context(self.store, [row['id']]))['excerpt'])

    def test_only_explicit_policy_patch_records_review_for_recovery_constraints(self):
        sources.seed_sources(self.store)
        source = self.store.get('source', 'source-world-bank')
        reviewed = sources.handle(self.store, 'PATCH', ['sources', source['id']],
            {'expected_version': source['version'], 'rights': RIGHTS}, {})
        self.assertEqual(reviewed['policy_reviewed_rights'], RIGHTS)
        at = reviewed['policy_reviewed_at']
        renamed = sources.handle(self.store, 'PATCH', ['sources', source['id']],
            {'expected_version': reviewed['version'], 'name': '[fixture] renamed'}, {})
        self.assertEqual(renamed['policy_reviewed_at'], at)
        self.assertNotIn('policy_reviewed_at', self.store.history('source', source['id'])[0])

    def test_search_pages_count_only_visible_matches_without_projecting_all_titles(self):
        for index in range(75):
            self.evidence(f'metadata-{index:02}', title='[fixture] stable needle', ingest_origin='manual',
                          rights={**RIGHTS, 'display': False})
        self.evidence('secret-body', excerpt='needle', ingest_origin='manual', rights={**RIGHTS, 'display': False})
        self.evidence('legal-body', excerpt='needle', ingest_origin='manual')
        original = self.store.policy_snapshots
        with patch.object(self.store, 'policy_snapshots', wraps=original) as selected:
            page = knowledge.handle(self.store, 'GET', ['evidence'], {}, {'search': 'needle', 'offset': 65, 'limit': 10})
        self.assertEqual(page['total'], 76)
        self.assertEqual(len(page['items']), 10)
        self.assertNotIn('secret-body', {row['id'] for row in page['items']})
        for row in page['items']:
            if row['id'].startswith('metadata-'):
                self.assertEqual(row['excerpt'], '')
        self.assertEqual(selected.call_count, 1)
        with patch.object(self.store, 'policy_snapshots', wraps=original) as selected:
            first = knowledge.handle(self.store, 'GET', ['evidence'], {}, {'search': 'needle', 'limit': 5})
        self.assertEqual(first['total'], 76)
        self.assertLessEqual(len(selected.call_args.args[0]), 7)
