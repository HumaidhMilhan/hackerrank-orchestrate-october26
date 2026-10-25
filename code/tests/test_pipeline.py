"""Independent fictional regression cases; no sample labels are imported here."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class IntentTests(unittest.TestCase):
    def test_multilingual_and_scoped_negation(self):
        from stage1 import fallback_intent
        examples = {
            'Ne supprimez pas mon compte.': 'NON_DELETION',
            'Veuillez supprimer mon compte.': 'DELETION',
            'No eliminen mi cuenta.': 'NON_DELETION',
            'Solicito la eliminación de mi cuenta.': 'DELETION',
            'このアカウントを削除してください。': 'DELETION',
            '계정 삭제를 요청합니다.': 'DELETION',
            'Export my data, then delete my account.': 'DELETION',
            'Do not send confirmation emails; delete my account.': 'DELETION',
            'Export my data; do not delete my account.': 'NON_DELETION',
            'Only unsubscribe me from marketing emails.': 'NON_DELETION',
            'Can you verify that my account was deleted?': 'DELETION',
            'Please confirm that my profile is gone and remaining records cannot identify me.': 'DELETION',
        }
        for text, expected in examples.items():
            with self.subTest(text=text):
                self.assertEqual(fallback_intent(text)[0], expected)

    def test_identity_history_does_not_merge_shared_phone(self):
        from stage1 import IdentityIndex
        users = [dict(user_id='person-a', email='new@example.test', phone='123', updated_at='2026-01-01T00:00:00Z'),
                 dict(user_id='person-b', email='other@example.test', phone='123', updated_at='2026-01-01T00:00:00Z')]
        history = [dict(audit_id='a1', user_id='person-a', event_time='2026-02-01T00:00:00Z', field_name='email', old_value='old@example.test', new_value='new@example.test')]
        case = dict(case_id='fixture', email='old@example.test', audit_at='2026-03-01T00:00:00Z')
        result = IdentityIndex(users, history).resolve(case, 'DELETION')
        self.assertEqual(result['user_ids'], ['person-a'])
        self.assertIn('new@example.test', result['identifiers'])
        self.assertNotIn('123', result['identifiers'])

    def test_future_identity_change_is_not_used(self):
        from stage1 import IdentityIndex
        history = [dict(audit_id='late', user_id='p', event_time='2027-01-01T00:00:00Z', field_name='email', old_value='old@example.test', new_value='new@example.test')]
        result = IdentityIndex([], history).resolve(dict(case_id='f', email='old@example.test', audit_at='2026-01-01T00:00:00Z'), 'DELETION')
        self.assertEqual(result['user_ids'], [])


class PolicyTests(unittest.TestCase):
    def test_independent_custom_cases(self):
        from evaluation.fixtures import run_fixtures
        for result in run_fixtures():
            with self.subTest(case=result['case_id']):
                self.assertTrue(result['passed'], result)

    def test_success_claim_does_not_erase_observed_replica(self):
        from evaluation.fixtures import context, obs, RULES
        from stage3 import assess_case
        from stage4 import build_output
        observations = [obs(facts={'resource_id': 'profile-demo', 'email': 'subject@example.test'}, scope='failover_replica'),
                        obs(facts={'event_type': 'DELETE_RECORD', 'reported_result': 'SUCCESS'}, when='2026-01-20T00:00:00Z', kind='claim')]
        assessment = assess_case(context(), observations, RULES)
        self.assertEqual(build_output(assessment)[0]['deletion_status'], 'INCOMPLETE')

    def test_clean_tombstone_keeps_stable_reference(self):
        from evaluation.fixtures import context, obs, RULES
        from stage3 import assess_case
        from stage4 import build_output
        import json
        evidence = obs(resource='ref', system='identity_service', category='ACCOUNT_TOMBSTONE',
                       facts={'subject_reference': 'subject-demo', 'email': None, 'phone': None, 'email_hash': None, 'name': None})
        row, _ = build_output(assess_case(context(), [evidence], RULES))
        self.assertEqual(row['deletion_status'], 'COMPLETE')
        self.assertEqual([s['operation'] for s in json.loads(row['steps_json'])], ['VERIFY_RECORD_REDACTED'])

    def test_same_time_conflict_remains_uncertain(self):
        from evaluation.fixtures import context, obs, RULES
        from stage3 import assess_case
        assessment = assess_case(context(), [obs(facts={'rows': 0}), obs(facts={'resource_id': 'profile-demo'}, evidence='other')], RULES)
        self.assertEqual(assessment['resources'][0]['assessment'], 'UNCERTAIN')

    def test_explicit_restore_denial_and_block_flags(self):
        from evaluation.fixtures import context, obs
        from stage3 import observed_state
        for facts, expected in [({'decision': 'deny', 'policy': 'privacy_deletion'}, 'BLOCKED'),
                                ({'eligible': 'true', 'deletion_block': 'false'}, 'ACTIVE'),
                                ({'eligible': 'true', 'deletion_block': 'true'}, 'BLOCKED')]:
            with self.subTest(facts=facts):
                self.assertEqual(observed_state(obs(category='BACKUP_ARCHIVE', facts=facts), context()), expected)

    def test_completed_identifier_lookup_establishes_attribution(self):
        from evaluation.fixtures import context, obs
        from stage3 import observed_state
        record = obs(category='ANALYTICS_PROFILE', facts={'event': 'contact_lookup_completed', 'rows': '1', 'lookup_key': 'subject@example.test'})
        self.assertEqual(observed_state(record, context()), 'IDENTIFIABLE')

    def test_best_evidence_and_conservative_comparison(self):
        from evaluation.fixtures import context, obs, RULES
        from stage3 import assess_case
        from stage4 import build_output
        assessment = assess_case(context(), [obs(facts={'rows': 0})], RULES, ['unread eligible evidence'])
        row, diagnostic = build_output(assessment)
        self.assertEqual(row['deletion_status'], 'INCOMPLETE')
        self.assertTrue(diagnostic['estimated'])
        self.assertEqual(build_output(assessment, 'incomplete')[0]['deletion_status'], 'INCOMPLETE')


class EvidenceTests(unittest.TestCase):
    def meta(self):
        return {'file_id': 'fixture-file', 'captured_at': '2026-01-01T00:00:00Z'}

    def test_log_trace_joins_identifier_to_completed_lookup(self):
        from stage2 import parse_logs
        lines = ('2026-01-01T00:00:00Z [DEBUG] [account_service] [tr-demo] profile_lookup_started: lookup_key="subject@example.test"\n'
                 '2026-01-01T00:00:01Z [INFO] [account_service] [tr-demo] profile_lookup_completed: resource_id="profile-demo" rows="0" http_status="404"')
        observations = parse_logs(self.meta(), lines)
        self.assertEqual(len(observations), 1)
        self.assertIn('subject@example.test', observations[0]['identifiers'])
        self.assertEqual(observations[0]['facts']['rows'], '0')

    def test_json_nested_observation_time(self):
        from stage2 import parse_json
        data = {'snapshots': [{'captured_at': '2025-12-01T00:00:00Z', 'data_store': 'account_service',
                              'collection': 'customer_profiles', 'records': [{'resource_id': 'profile-demo', 'email': 'subject@example.test'}]}]}
        result = parse_json(self.meta(), data)[0]
        self.assertEqual(result['observed_at'], '2025-12-01T00:00:00Z')
        self.assertEqual(result['captured_at'], '2026-01-01T00:00:00Z')

    def test_heartbeat_and_restore_evaluation_are_direct_observations(self):
        from stage2 import parse_logs
        text = ('2026-01-01T00:00:00Z service=integration_service event=connector_heartbeat resource_id=data_flow_demo enabled=true\n'
                '2026-01-01T00:00:00Z service=backup_service event=restore_candidate_evaluated resource_id=backup_demo eligible=true deletion_block=false\n'
                '2026-01-01T00:00:00Z service=support_platform event=attachment_pii_scan resource_id=support_demo matched_value=subject@example.test')
        rows = parse_logs(self.meta(), text)
        self.assertTrue(all(row['kind'] == 'observation' for row in rows))
        self.assertEqual(rows[-1]['category'], 'SUPPORT_ATTACHMENT')

    def test_sql_preserves_replica_scope_and_blocks_attach(self):
        from stage2 import parse_sql
        import sqlite3
        text = "CREATE TABLE customer_profiles_failover_replica(resource_id TEXT,email TEXT); INSERT INTO customer_profiles_failover_replica VALUES('profile-demo','subject@example.test');"
        result = parse_sql(self.meta(), text)[0]
        self.assertEqual(result['scope'], 'failover_replica')
        with self.assertRaises(sqlite3.DatabaseError):
            parse_sql(self.meta(), "ATTACH DATABASE ':memory:' AS external;")

    def test_source_ownership_can_recover_subject_without_current_snapshot(self):
        from collections import defaultdict
        from evaluation.fixtures import context, obs
        from stage2 import EvidenceStore
        class Offline:
            enabled = False
        store = EvidenceStore(Path('.'), Offline(), Path('.'))
        profile = obs(facts={'email': 'subject@example.test', 'customer_reference': 'user_demo'})
        profile['identifiers'] = ['subject@example.test', 'user_demo']
        audit = obs(resource='audit-demo', system='security_service', category='SECURITY_AUDIT_LOG', facts={'subject_reference': 'user_demo'})
        audit['identifiers'] = ['user_demo']
        store.by_identifier = defaultdict(list, {'subject@example.test': [profile], 'user_demo': [profile, audit]})
        store.by_resource = defaultdict(list, {'profile-demo': [profile], 'audit-demo': [audit]})
        ctx = context(); ctx['identifiers'] = ['subject@example.test']; ctx['user_ids'] = []
        self.assertEqual({r['resource_id'] for r in store.retrieve(ctx)}, {'profile-demo', 'audit-demo'})


class ProviderTests(unittest.TestCase):
    def test_malformed_response_and_failure_usage_are_recorded(self):
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        from llm import ModelClient
        from sdk_fakes import FakeSDK
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'GEMINI_API_KEY': 'fixture-key', 'GEMINI_TEXT_MODEL': 'fixture-model'}):
            client = ModelClient(Path(temp))
            sdk = FakeSDK()
            sdk.models.generate_content.return_value = SimpleNamespace(text=None, usage_metadata=None)
            with patch('llm.genai.Client', return_value=sdk):
                with self.assertLogs('audit', 'WARNING'):
                    self.assertIsNone(client.request_json('fixture', 'fixture text', {'type': 'ARRAY'}))
            self.assertEqual(len(client.calls), 2)
            self.assertFalse(client.calls[-1]['success'])
            self.assertIsNone(client.calls[-1]['input_tokens'])
            client.close()

    def test_invalid_model_intent_uses_fallback_and_not_final_status(self):
        from stage1 import interpret_requests
        class FakeClient:
            enabled = True
            calls = 0
            def request_json(self, *args, **kwargs):
                self.calls += 1
                return [{'case_id': 'demo', 'intent': 'COMPLETE', 'supporting_phrase': 'invented'}]
        client = FakeClient()
        with self.assertLogs('audit', 'WARNING'):
            result = interpret_requests([{'case_id': 'demo', 'request_text': 'Please delete my account.'}], client)
        self.assertEqual(client.calls, 2)
        self.assertEqual(result['demo']['intent'], 'DELETION')
        self.assertEqual(result['demo']['method'], 'rules')


class CliTests(unittest.TestCase):
    def test_archive_has_required_report_paths_and_excludes_private_files(self):
        import tempfile
        import zipfile
        from main import package_code
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'code/evaluation').mkdir(parents=True)
            for name in ['evaluation_report.md', 'usage_report.md']:
                (root / 'code/evaluation' / name).write_text('Fictional test report.', encoding='utf-8')
            (root / '.env').write_text('PRIVATE=fixture', encoding='utf-8')
            (root / 'dataset').mkdir(); (root / 'dataset/private.csv').write_text('fictional')
            with zipfile.ZipFile(package_code(root)) as archive:
                self.assertIn('evaluation/evaluation_report.md', archive.namelist())
                self.assertIn('evaluation/usage_report.md', archive.namelist())
                self.assertNotIn('.env', archive.namelist())
                self.assertNotIn('dataset/private.csv', archive.namelist())

    def test_offline_progress_output_and_resume(self):
        import contextlib
        import csv
        import io
        import json
        import tempfile
        from unittest.mock import patch
        import main
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / 'inputs'
            (dataset / 'evidence').mkdir(parents=True)
            def write(name, fields, rows):
                with (dataset / name).open('w', encoding='utf-8', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader(); writer.writerows(rows)
            write('deletion_requests.csv', ['case_id', 'email', 'audit_at', 'request_text'],
                  [{'case_id': 'a', 'email': 'subject@example.test', 'audit_at': '2026-02-01T00:00:00Z', 'request_text': 'Delete my account.'},
                   {'case_id': 'b', 'email': 'other@example.test', 'audit_at': '2026-02-01T00:00:00Z', 'request_text': 'Do not delete my account.'},
                   {'case_id': 'c', 'email': 'missing@example.test', 'audit_at': '2026-02-01T00:00:00Z', 'request_text': 'Delete my account.'}])
            write('user_identities.csv', ['user_id', 'email', 'updated_at'], [])
            write('user_audit_log.csv', ['audit_id', 'user_id', 'event_time'], [])
            write('system_activity.csv', ['activity_id', 'event_time'], [])
            write('deletion_rules.csv', ['rule_id', 'data_category', 'required_action'], [{'rule_id': 'r', 'data_category': 'USER_PROFILE', 'required_action': 'DELETE'}])
            write('evidence_files.csv', ['file_id', 'file_path', 'captured_at'], [{'file_id': 'source', 'file_path': 'evidence/source.json', 'captured_at': '2026-01-01T00:00:00Z'}])
            (dataset / 'evidence/source.json').write_text(json.dumps({'records': [{'system': 'account_service', 'resource_id': 'profile-demo',
                                                                               'record_type': 'USER_PROFILE', 'result': 'NOT_FOUND', 'subject_reference': 'subject@example.test'}]}))
            arguments = ['--dataset', str(dataset), '--output', str(root / 'result.csv'), '--offline']
            stderr, stdout = io.StringIO(), io.StringIO()
            with patch.object(main, 'ROOT', root), contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
                self.assertEqual(main.main(arguments), 0)
                first = (root / 'result.csv').read_bytes()
                self.assertEqual(main.main(arguments + ['--resume', '--quiet']), 0)
            self.assertEqual(first, (root / 'result.csv').read_bytes())
            self.assertEqual(stdout.getvalue(), '')
            for token in ['EXTRACT', 'CASE', 'DONE', 'WARNING', 'RESUME']:
                self.assertIn(token, stderr.getvalue())
            rows = list(csv.DictReader(io.StringIO(first.decode())))
            self.assertEqual([r['deletion_status'] for r in rows], ['COMPLETE', 'NOT_APPLICABLE', 'INCOMPLETE'])
            assessments=json.loads((root/'.runtime/assessments-evaluation.json').read_text(encoding='utf-8'))
            self.assertTrue(assessments['c'].get('recheck_used',False),'empty retrieval needs one bounded recheck')
            self.assertFalse(assessments['a'].get('recheck_used',False))
            self.assertFalse(assessments['b'].get('recheck_used',False))

    def test_metric_empty_and_missing_steps(self):
        from evaluation.main import evaluate
        empty = [{'case_id': 'a', 'deletion_status': 'NOT_APPLICABLE', 'steps_json': '[]'}]
        result = evaluate(empty, empty)
        self.assertEqual(result['sequence_accuracy'], 1)
        self.assertEqual(result['step_f1'], 1)

    def test_quiet_and_verbose_are_exclusive(self):
        import contextlib
        import io
        from main import parse_args
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(['--quiet', '--verbose'])


class ReviewRegressionTests(unittest.TestCase):
    def prepare_store(self, root, records, activities=None, extra_files=None):
        import csv
        import json
        from llm import ModelClient
        from stage2 import EvidenceStore
        (root / 'evidence').mkdir(exist_ok=True)
        (root / 'evidence/records.json').write_text(json.dumps({'records': records}), encoding='utf-8')
        manifest = [{'file_id': 'record-source', 'file_path': 'evidence/records.json', 'captured_at': '2026-01-01T00:00:00Z'}] + (extra_files or [])
        with (root / 'evidence_files.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['file_id', 'file_path', 'captured_at']); writer.writeheader(); writer.writerows(manifest)
        with (root / 'system_activity.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['activity_id', 'event_time', 'event_type', 'source_system', 'target_system', 'resource_id', 'reported_result', 'details'])
            writer.writeheader(); writer.writerows(activities or [])
        return EvidenceStore(root, ModelClient(root / 'models', offline=True), root / 'extract').prepare()

    def test_shared_phone_does_not_attribute_another_subject(self):
        import tempfile
        from evaluation.fixtures import context
        with tempfile.TemporaryDirectory() as temp:
            store = self.prepare_store(Path(temp), [{'resource_id': 'account_other', 'record_type': 'USER_PROFILE', 'system': 'account_service',
                                                    'user_id': 'user_other', 'email': 'other@example.test', 'phone': '+123456789'}])
            ctx = context(); ctx['user_ids'] = ['user_subject']; ctx['identifiers'].append('+123456789')
            self.assertEqual(store.retrieve(ctx), [])

    def test_structured_resource_link_is_followed(self):
        import tempfile
        from evaluation.fixtures import context
        with tempfile.TemporaryDirectory() as temp:
            store = self.prepare_store(Path(temp), [
                {'resource_id': 'account_source', 'system': 'account_service', 'record_type': 'USER_PROFILE', 'email': 'subject@example.test', 'target_resource_id': 'export_linked'},
                {'resource_id': 'export_linked', 'system': 'export_service', 'record_type': 'USER_EXPORT', 'object_key': 'fictional/export'}])
            self.assertEqual({o['resource_id'] for o in store.retrieve(context())}, {'account_source', 'export_linked'})

    def test_system_names_in_activity_prose_do_not_join_unrelated_resources(self):
        import tempfile
        from evaluation.fixtures import context
        def activity(resource):
            return {'activity_id': 'event-' + resource, 'event_time': '2026-01-01T00:00:00Z', 'event_type': 'DELETE_RECORD',
                    'source_system': 'account_service', 'target_system': 'account_service', 'resource_id': resource,
                    'reported_result': 'SUCCESS', 'details': 'Record read from account_service.'}
        with tempfile.TemporaryDirectory() as temp:
            store = self.prepare_store(Path(temp), [
                {'resource_id': 'account_source', 'system': 'account_service', 'record_type': 'USER_PROFILE', 'email': 'subject@example.test'},
                {'resource_id': 'account_other', 'system': 'account_service', 'record_type': 'USER_PROFILE', 'email': 'other@example.test'}],
                [activity('account_source'), activity('account_other')])
            self.assertEqual({o['resource_id'] for o in store.retrieve(context())}, {'account_source'})

    def test_reverse_restore_link_is_discoverable_from_downstream(self):
        import tempfile
        from evaluation.fixtures import context
        activity = {'activity_id': 'restore-event', 'event_time': '2026-01-01T00:00:00Z', 'event_type': 'RESTORE_BACKUP',
                    'source_system': 'backup_service', 'target_system': 'search_service', 'resource_id': 'backup_demo',
                    'reported_result': 'SUCCESS', 'details': 'Restore job repopulated downstream resource search_demo.'}
        with tempfile.TemporaryDirectory() as temp:
            store = self.prepare_store(Path(temp), [
                {'resource_id': 'search_demo', 'system': 'search_service', 'record_type': 'SEARCH_INDEX_ENTRY', 'email': 'subject@example.test'},
                {'resource_id': 'backup_demo', 'system': 'backup_service', 'record_type': 'BACKUP_ARCHIVE', 'restore_allowed': True}], [activity])
            self.assertIn('backup_demo', {o['resource_id'] for o in store.retrieve(context())})

    def test_partial_payload_or_treatment_label_is_not_verified_anonymization(self):
        from evaluation.fixtures import context, obs
        from stage3 import observed_state
        for facts in [{'email': None}, {'result': 'ANONYMIZED'}, {'email': None, 'phone': None, 'email_hash': None}]:
            self.assertEqual(observed_state(obs(category='ANALYTICS_PROFILE', facts=facts), context()), 'UNKNOWN')

    def test_invalid_intent_retry_makes_a_new_network_call(self):
        import tempfile
        from unittest.mock import patch
        from llm import ModelClient
        from stage1 import interpret_requests
        from sdk_fakes import FakeSDK, response
        def envelope(phrase):
            return response([{'case_id': 'demo', 'intent': 'DELETION', 'supporting_phrase': phrase}])
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'GEMINI_API_KEY': 'fixture-key', 'GEMINI_TEXT_MODEL': 'fixture-model'}):
            client = ModelClient(Path(temp))
            sdk = FakeSDK()
            sdk.models.generate_content.side_effect = [envelope('invented'), envelope('delete my account')]
            with patch('llm.genai.Client', return_value=sdk):
                with self.assertLogs('audit', 'WARNING'):
                    result = interpret_requests([{'case_id': 'demo', 'request_text': 'Please delete my account.'}], client)
            self.assertEqual(sdk.models.generate_content.call_count, 2)
            self.assertEqual(result['demo']['method'], 'model')
            client.close()

    def test_failed_pdf_vision_preserves_partial_data_and_is_not_cached(self):
        import tempfile
        import pymupdf
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'evidence').mkdir()
            document = pymupdf.open()
            page = document.new_page(); page.insert_text((50, 60), 'Account account_demo belongs to subject@example.test; profile detail.')
            document.new_page()  # unreadable/empty second page requires vision
            document.save(root / 'evidence/partial.pdf'); document.close()
            store = self.prepare_store(root, [], extra_files=[{'file_id': 'pdf-source', 'file_path': 'evidence/partial.pdf', 'captured_at': '2026-01-01T00:00:00Z'}])
            self.assertEqual([r['file_id'] for r in store.failures], ['pdf-source'])
            self.assertTrue(any(o['resource_id'] == 'account_demo' for o in store.observations))
            # Only the successful empty JSON extraction is cached, not the partial PDF.
            self.assertEqual(len(list((root / 'extract').glob('*.json'))), 1)

    def test_active_retained_only_flow_is_not_a_deletion_risk(self):
        from evaluation.fixtures import context, obs, RULES
        from stage3 import assess_case
        observation = obs(resource='flow-demo', system='integration_service', category='DATA_FLOW',
                          facts={'enabled': True, 'data_categories': ['LEGAL_HOLD_RECORD'], 'subject_selector': 'subject@example.test'})
        assessment = assess_case(context(), [observation], {**RULES, 'LEGAL_HOLD_RECORD': {'rule_id': 'hold', 'required_action': 'RETAIN'}})
        self.assertFalse(any(r['assessment'] == 'VIOLATION' and r['action'] == 'DISABLE' for r in assessment['resources']))

    def test_active_flow_with_unknown_payload_stays_uncertain(self):
        from evaluation.fixtures import context, obs, RULES
        from stage3 import assess_case
        assessment = assess_case(context(), [obs(resource='flow-demo', system='integration_service', category='DATA_FLOW', facts={'enabled': True})], RULES)
        self.assertEqual(assessment['resources'][0]['assessment'], 'UNCERTAIN')


if __name__ == '__main__':
    unittest.main()
