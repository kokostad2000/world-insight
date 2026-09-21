"""Real loopback HTTP/SQLite access policy tests; isolated fixtures, no upstream."""
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from server.app import Application, handler_class
from server.modules import knowledge, research, sources
from server.platform.config import load_config
from server.platform.store import Store


BODY = 'LICENSED_BODY_PRIVATE_FIXTURE_90814'
TRANSLATION = 'LICENSED_TRANSLATION_PRIVATE_FIXTURE_09131'
NOTE = 'AUTHORED_NOTE_KEEP_FIXTURE_71251'
GRANTED = {'fetch': True, 'store': True, 'display': True, 'export': True, 'ai': False}


class EvidenceAccessHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='world-insight-rights-http-fixture-')
        self.config = load_config(data_dir=Path(self.tmp.name) / 'data', port=8874)
        self.store = Store(self.config['db_path'])
        sources.seed_sources(self.store)
        self.app = Application(self.config, self.store, {'instance_id': 'rights-http-fixture'})
        self.server = ThreadingHTTPServer(('127.0.0.1', 8874), handler_class(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        self.topic = self.api('topics', {'question': '[fixture] access and export', 'is_fixture': True})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.tmp.cleanup()

    def request(self, path, body=None, method=None):
        connection = http.client.HTTPConnection('127.0.0.1', 8874, timeout=10)
        connection.request(method or ('POST' if body is not None else 'GET'), '/api/' + path,
            body=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        status, content = response.status, response.read()
        connection.close()
        return status, json.loads(content)

    def api(self, path, body=None, method=None):
        status, value = self.request(path, body, method)
        self.assertEqual(status, 200, (path, value))
        return value

    def evidence(self, **extra):
        return self.api('evidence', {'source_id': 'source-world-bank', 'topic_id': self.topic['id'],
            'title': '[fixture] licensed source material', 'url': 'https://fixture.example/' + str(uuid.uuid4()),
            'excerpt': BODY, 'translation': TRANSLATION, 'notes': NOTE, 'rights': GRANTED, 'is_fixture': True, **extra})

    def source_patch(self, source_id='source-world-bank', **extra):
        source = self.store.get('source', source_id)
        return self.api('sources/' + source_id, {'expected_version': source['version'], **extra}, 'PATCH')

    def cite(self, evidence):
        return self.api('judgments', {'topic_id': self.topic['id'], 'conclusion': '[fixture] authored judgment',
            'evidence_version_ids': [evidence['version_id']], 'is_fixture': True})

    def drain(self):
        for _ in range(8):
            if not self.app.drain():
                break

    def assert_private_absent(self, result):
        raw = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(BODY, raw)
        self.assertNotIn(TRANSLATION, raw)
        self.assertNotIn(hashlib.sha256(BODY.encode()).hexdigest(), raw)

    def read_paths(self, row):
        return ['evidence?limit=200', 'evidence?status=unverified&limit=200',
            'evidence?similar_to=' + row['id'], 'evidence/' + row['id'], 'evidence/' + row['id'] + '/history',
            'evidence/' + row['id'] + '/backlinks', 'topics/' + self.topic['id'] + '/bundle',
            'exports?topic_id=' + self.topic['id'] + '&format=json', 'exports?topic_id=' + self.topic['id'] + '&format=markdown']

    def test_actual_read_history_backlink_bundle_and_export_entrypoints_share_one_context(self):
        row = self.evidence()
        self.cite(row)
        self.evidence(title='[fixture] licensed source material, another report')
        self.api('evidence/' + row['id'], {'expected_version': row['version'], 'notes': NOTE + ' revised'}, 'PATCH')
        self.source_patch(rights={**GRANTED, 'display': False, 'export': False})
        for path in self.read_paths(row):
            with self.subTest(path=path), patch.object(knowledge, 'build_policy_context', wraps=knowledge.build_policy_context) as build:
                result = self.api(path)
                self.assert_private_absent(result)
                self.assertEqual(build.call_count, 1, path)
        detail = self.api('evidence/' + row['id'])
        self.assertIn(NOTE, detail['notes'])
        self.assertTrue(detail['rights']['display'])
        self.assertFalse(detail['effective_rights']['display'])
        self.assertTrue(detail['relations']['judgment'])
        self.assertEqual(self.store.version(row['version_id'])['excerpt'], BODY)

    def test_hidden_body_and_translation_cannot_be_found_through_search(self):
        row = self.evidence()
        self.source_patch(rights={**GRANTED, 'display': False})
        for needle in (BODY, TRANSLATION, hashlib.sha256(BODY.encode()).hexdigest()):
            for filters in ('', '&status=unverified'):
                result = self.api('evidence?search=' + quote(needle) + filters)
                self.assertEqual(result['total'], 0)
                self.assertEqual(result['items'], [])
        self.assertEqual(self.api('evidence?search=' + quote(NOTE))['items'][0]['id'], row['id'])

    def test_writes_duplicate_corrections_and_split_never_echo_restricted_body(self):
        self.source_patch(rights={**GRANTED, 'display': False, 'export': False})
        url = 'https://fixture.example/write-receipt'
        channels = [{'source_id': 'source-world-bank', 'url': url},
            {'source_id': 'source-world-bank', 'url': url + '/other'}]
        with patch.object(knowledge, 'build_policy_context', wraps=knowledge.build_policy_context) as build:
            row = self.evidence(url=url, channels=channels)
            self.assertEqual(build.call_count, 1)
        self.assert_private_absent(row)
        self.assertEqual(self.store.get('evidence', row['id'])['excerpt'], BODY)
        duplicate = self.evidence(url=url)
        self.assertTrue(duplicate['deduplicated'])
        self.assert_private_absent(duplicate)
        edited = self.api('evidence/' + row['id'], {'expected_version': duplicate['version'], 'notes': NOTE + ' edit'}, 'PATCH')
        self.assert_private_absent(edited)
        corrected = self.api('evidence/' + row['id'] + '/corrections', {'expected_version': edited['version'],
            'status': 'corrected', 'substantive': True, 'reason': '[fixture] actual human correction'})
        self.assert_private_absent(corrected)
        with patch.object(knowledge, 'build_policy_context', wraps=knowledge.build_policy_context) as build:
            split = self.api('evidence/' + row['id'] + '/split', {'expected_version': corrected['version'],
                'channels': [channels[1]], 'reason': '[fixture] separate appearance'})
            self.assertEqual(build.call_count, 1)
        self.assert_private_absent(split)
        self.assertIn(NOTE, split['split']['notes'])
        self.assertEqual(self.store.get('evidence', split['split']['id'])['excerpt'], BODY)

    def test_source_deadline_hides_history_and_exports_before_background_cleanup(self):
        with patch.object(self.store, 'now', return_value='2026-01-01T00:00:00Z'):
            row = self.evidence()
            self.cite(row)
        self.source_patch(retention_days=7)
        for path in self.read_paths(row):
            self.assert_private_absent(self.api(path))
        detail = self.api('evidence/' + row['id'])
        self.assertTrue(detail['content_expired'])
        self.assertEqual(detail['content_expires_at'], '2026-01-08T00:00:00.000000Z')
        self.assertEqual(detail['notes'], NOTE)
        self.assertEqual(self.store.get('evidence', row['id'])['excerpt'], BODY)
        self.assertFalse(self.store.get('evidence', row['id']).get('content_expired', False))

    def test_ordinary_export_keeps_unexpired_licensed_body_and_marks_deadline(self):
        with patch.object(self.store, 'now', return_value='2026-09-21T00:00:00Z'):
            self.source_patch(retention_days=7)
            row = self.evidence()
            self.cite(row)
            data = self.api('exports?topic_id=' + self.topic['id'])
            markdown = self.api('exports?topic_id=' + self.topic['id'] + '&format=markdown')['content']
        self.assertEqual(data['citations'][0]['excerpt'], BODY)
        self.assertEqual(data['citations'][0]['content_expires_at'], '2026-09-28T00:00:00.000000Z')
        self.assertIn(BODY, markdown)
        self.assertIn('正文保留截止：2026-09-28', markdown)

    def test_due_collector_is_hidden_while_historical_notes_remain_protected(self):
        with patch.object(self.store, 'now', return_value='2026-01-01T00:00:00Z'):
            first = knowledge.ingest(self.store, {'source_id': 'source-world-bank', 'title': '[fixture] untouched candidate',
                'excerpt': BODY, 'translation': TRANSLATION, 'rights': GRANTED, 'topic_id': self.topic['id']}, origin='collector')
            noted = knowledge.ingest(self.store, {'source_id': 'source-world-bank', 'title': '[fixture] candidate with note',
                'excerpt': BODY, 'rights': GRANTED, 'topic_id': self.topic['id'], 'notes': NOTE}, origin='collector')
        self.store.update('evidence', noted['id'], {'notes': '', 'manually_touched': False}, noted['version'])
        self.assert_private_absent(self.api('evidence/' + first['id']))
        self.assertEqual(self.api('evidence/' + noted['id'])['excerpt'], BODY)
        self.assertEqual(self.store.get('evidence', first['id'])['excerpt'], BODY)

    def test_collector_receipt_preserves_stored_content_and_links_without_full_scan(self):
        with patch.object(knowledge, 'build_policy_context', wraps=knowledge.build_policy_context) as build:
            row = knowledge.ingest(self.store, {'source_id': 'source-world-bank', 'title': '[fixture] collector receipt',
                'excerpt': BODY, 'translation': TRANSLATION, 'notes': NOTE, 'rights': GRANTED,
                'source_record_id': 'indicator:USA:2025', 'topic_id': self.topic['id']}, origin='collector')
            self.assertEqual(build.call_count, 0)
        self.assert_private_absent(row)
        self.assertEqual(row['notes'], NOTE)
        self.assertEqual(row['source_record_id'], 'indicator:USA:2025')
        self.assertEqual(row['response_mode'], 'collector_receipt')
        self.assertEqual(row['ingest_origin'], 'collector')
        self.assertEqual(self.store.version(row['version_id'])['excerpt'], BODY)

    def test_manual_and_legacy_unknown_licence_never_implicitly_grant_body(self):
        status, _ = self.request('evidence', {'title': '[fixture] undeclared manual', 'excerpt': BODY})
        self.assertEqual(status, 400)
        explicit = self.evidence(source_id='manual')
        self.assertEqual(explicit['excerpt'], BODY)
        legacy = self.store.create('evidence', {'title': '[fixture] imported unknown rights', 'source_id': 'manual',
            'excerpt': BODY, 'translation': TRANSLATION, 'notes': NOTE, 'is_fixture': True})
        detail = self.api('evidence/' + legacy['id'])
        self.assert_private_absent(detail)
        self.assertEqual(detail['notes'], NOTE)

    def test_trash_restore_response_preserves_notes_without_reviving_restricted_body(self):
        row = self.evidence()
        self.source_patch(rights={**GRANTED, 'display': False, 'export': False})
        current = self.store.get('evidence', row['id'])
        trashed = self.store.update('evidence', row['id'], {'deleted': True, 'deleted_reason': '[fixture] explicit trash'}, current['version'])
        self.assert_private_absent(self.api('evidence/' + row['id'] + '/history'))
        restored = self.api('trash/evidence/' + row['id'] + '/restore', {'expected_version': trashed['version'], 'reason': '[fixture] explicit restore'})
        self.assert_private_absent(restored)
        self.assertEqual(restored['notes'], NOTE)
        self.assertFalse(restored['deleted'])
        self.assertEqual(self.store.get('evidence', row['id'])['excerpt'], BODY)

    def test_correction_and_split_cannot_persist_expired_body_again(self):
        url = 'https://fixture.example/expired-split'
        channels = [{'source_id': 'source-world-bank', 'url': url}, {'source_id': 'source-world-bank', 'url': url + '/other'}]
        row = self.evidence(url=url, channels=channels)
        expired = knowledge.expire_content(self.store, row['id'], row['version'], '[fixture] licensed content expired', 'fixture-content-expired')
        corrected = self.api('evidence/' + row['id'] + '/corrections', {'expected_version': expired['version'],
            'status': 'corrected', 'substantive': True, 'reason': '[fixture] metadata correction', 'excerpt': BODY})
        self.assert_private_absent(corrected)
        self.assertEqual(self.store.get('evidence', row['id'])['excerpt'], '')
        split = self.api('evidence/' + row['id'] + '/split', {'expected_version': corrected['version'],
            'channels': [channels[1]], 'reason': '[fixture] preserve expired state'})
        self.assert_private_absent(split)
        self.assertTrue(self.store.get('evidence', split['split']['id'])['content_expired'])

    def test_source_patch_drives_m3_m4_m5_and_replay_is_idempotent(self):
        row = self.evidence()
        judgment = self.cite(row)
        claim = self.api('claims', {'subject': '[fixture] author', 'statement': '[fixture] claim',
            'evidence_version_ids': [row['version_id']], 'topic_id': self.topic['id']})
        event = self.api('events', {'title': '[fixture] reported action', 'claim_ids': [claim['id']], 'topic_id': self.topic['id']})
        scenario = self.api('scenarios', {'title': '[fixture] possible outcome', 'description': '[fixture] conditional development',
            'topic_id': self.topic['id'], 'evidence_version_ids': [row['version_id']]})
        path = self.api('impact-paths', {'title': '[fixture] path', 'topic_id': self.topic['id'], 'nodes': [{'id': 'a', 'label': 'a'}, {'id': 'b', 'label': 'b'}],
            'edges': [{'from': 'a', 'to': 'b', 'status': 'assumption', 'evidence_version_ids': [row['version_id']]}]})
        brief = self.api('briefs', {'topic_id': self.topic['id']})
        self.drain()
        self.source_patch(rights={**GRANTED, 'display': False, 'export': False})
        self.drain()
        updated = self.store.get('evidence', row['id'])
        self.assertTrue(updated['needs_review'])
        self.assertEqual(updated['rights'], self.store.version(row['version_id'])['rights'])
        self.assertEqual(self.store.get('claim', claim['id'])['dispute_status'], 'needs_review')
        self.assertEqual(self.store.get('event', event['id'])['verification_status'], 'needs_review')
        for kind, record in [('judgment', judgment), ('scenario', scenario), ('impact_path', path), ('brief', brief)]:
            self.assertEqual(self.store.get(kind, record['id'])['status'], 'needs_review')
        self.assertTrue(self.store.all('notification'))
        raw = dict(self.store.db.execute("SELECT * FROM outbox WHERE type='source.policy_changed'").fetchone())
        raw['payload'] = json.loads(raw['payload'])
        before = self.store.snapshots()
        knowledge.on_event(self.store, raw)
        self.drain()
        self.assertEqual(self.store.snapshots(), before)
        self.assertEqual(self.store.version(row['version_id'])['excerpt'], BODY)
        self.assertTrue(self.store.integrity()['ok'])

    def test_source_policy_consumer_failure_rolls_back_owned_updates_and_retries(self):
        row = self.evidence()
        judgment = self.cite(row)
        self.drain()
        with patch.object(research, 'on_event', side_effect=RuntimeError('fixture consumer failure')):
            self.source_patch(rights={**GRANTED, 'export': False})
        self.assertEqual(self.store.get('evidence', row['id'])['version'], row['version'])
        pending = self.store.db.execute("SELECT delivered_at, attempts FROM outbox WHERE type='source.policy_changed'").fetchone()
        self.assertIsNone(pending[0])
        self.assertEqual(pending[1], 1)
        self.drain()
        self.assertTrue(self.store.get('evidence', row['id'])['needs_review'])
        self.assertEqual(self.store.get('judgment', judgment['id'])['status'], 'needs_review')

    def test_historical_removed_channel_and_origin_receive_source_change(self):
        row = self.evidence(channels=[{'source_id': 'source-fed', 'url': 'https://fixture.example/old-channel'}])
        current = self.api('evidence/' + row['id'], {'expected_version': row['version'],
            'channels': [{'source_id': 'source-world-bank', 'url': row['url']}]}, 'PATCH')
        derived = self.evidence(origin_evidence_id=row['id'])
        self.source_patch('source-fed', rights={**GRANTED, 'export': False})
        self.drain()
        for target in (current, derived):
            self.assertTrue(self.store.get('evidence', target['id'])['needs_review'])
        self.assert_private_absent(self.api('exports?topic_id=' + self.topic['id']))

    def test_selected_countries_and_sources_filter_legacy_background_without_rewriting_citations(self):
        usa = self.evidence(title='[fixture] USA metric')
        china = self.evidence(source_id='source-fed', title='[fixture] CHN manually cited', topic_id=None)
        for code, source_id, ref in [('USA', 'source-world-bank', usa['version_id']), ('CHN', 'source-world-bank', china['version_id']), ('USA', 'source-fed', china['version_id'])]:
            knowledge.upsert_observation(self.store, {'topic_id': self.topic['id'], 'source_id': source_id,
                'country_code': code, 'indicator': 'population', 'unit': 'people', 'period': '2025', 'value': 0, 'evidence_version_ids': [ref], 'is_fixture': True})
        self.cite(china)
        self.api('topics/' + self.topic['id'], {'expected_version': self.topic['version'],
            'country_codes': ['USA'], 'source_ids': ['source-world-bank']}, 'PATCH')
        data = self.api('topics/' + self.topic['id'] + '/bundle')
        self.assertEqual([(row['country_code'], row['source_id']) for row in data['observations']], [('USA', 'source-world-bank')])
        self.assertIn(china['version_id'], [row['version_id'] for row in data['citations']])
        self.assertEqual(len(self.store.all('observation', topic_id=self.topic['id'])), 3)
        self.assertEqual(self.store.get('evidence', china['id'])['topic_id'], None)


if __name__ == '__main__':
    unittest.main()
