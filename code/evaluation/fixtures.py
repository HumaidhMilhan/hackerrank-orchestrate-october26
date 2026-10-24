"""Participant-created, fictional cases with explicit expected behavior."""
from stage1 import fallback_intent
from stage3 import assess_case
from stage4 import build_output

RULES = {category: {'rule_id': 'fixture-' + category.lower(), 'required_action': action}
         for category, action in [('USER_PROFILE', 'DELETE'), ('ACCOUNT_TOMBSTONE', 'REDACT'),
                                  ('BACKUP_ARCHIVE', 'RETAIN'), ('SECURITY_AUDIT_LOG', 'RETAIN')]}


def obs(resource='profile-demo', system='account_service', category='USER_PROFILE', facts=None,
        evidence='fixture-source', when='2026-01-01T00:00:00Z', captured=None, scope='primary', kind='observation'):
    return {'resource_id': resource, 'system_id': system, 'category': category, 'facts': facts or {},
            'evidence_id': evidence, 'observed_at': when, 'captured_at': captured or when,
            'scope': scope, 'kind': kind, 'location': 'fictional fixture', 'identifiers': []}


def context(case_id='fixture', intent='DELETION'):
    return {'case_id': case_id, 'audit_at': '2026-02-01T00:00:00Z', 'intent': intent,
            'identifiers': ['subject@example.test', 'subject-demo'], 'warnings': []}


def run_fixtures():
    results = []
    cases = [
        ('Multilingual explicit non-deletion', context('custom-negation', fallback_intent('Ne supprimez pas mon compte.')[0]), [],
         'NOT_APPLICABLE', [], 'French negation must precede affirmative deletion stems.'),
        ('Primary absent, replica present', context('custom-replica'),
         [obs(facts={'rows': '0'}), obs(facts={'resource_id': 'profile-demo', 'email': 'subject@example.test'}, evidence='replica-source', scope='failover_replica')],
         'INCOMPLETE', ['REPORT_REMAINING_RECORD', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT'],
         'A primary absence cannot erase replica presence; cite replica-source.'),
        ('Tombstone exposes an email hash', context('custom-tombstone'),
         [obs(resource='reference-demo', system='identity_service', category='ACCOUNT_TOMBSTONE',
              facts={'resource_id': 'reference-demo', 'subject_reference': 'subject-demo', 'email': None, 'phone': None,
                     'name': None, 'email_hash': 'f' * 64, 'account_status': 'DELETED'})],
         'INCOMPLETE', ['REPORT_EXPOSED_PII', 'REDACT_RECORD', 'VERIFY_RECORD_REDACTED'],
         'Keep the stable subject reference; redact the exposed hash.'),
        ('Ignore an after-cutoff capture', context('custom-cutoff'),
         [obs(facts={'rows': '0'}), obs(facts={'resource_id': 'profile-demo', 'email': 'subject@example.test'},
                                     evidence='future-source', captured='2026-03-01T00:00:00Z')],
         'COMPLETE', ['VERIFY_RECORD_ABSENT'], 'A later capture is ineligible even when its embedded observation time is earlier.'),
        ('Disable flows and block restores before cleanup', context('custom-recreation'),
         [obs(resource='connector-demo', system='integration_service', category='DATA_FLOW',
              facts={'enabled': True, 'source_resource_id': 'profile-demo', 'subject_selector': 'subject@example.test'}),
          obs(resource='archive-demo', system='backup_service', category='BACKUP_ARCHIVE', facts={'restore_allowed': True}),
          obs(facts={'resource_id': 'profile-demo'})],
         'INCOMPLETE', ['REPORT_REMAINING_RECORD', 'REPORT_ACTIVE_DATA_FLOW', 'REPORT_RESTORE_RISK',
                        'DISABLE_DATA_FLOW', 'BLOCK_RESTORE', 'DELETE_RECORD', 'VERIFY_RECORD_ABSENT',
                        'VERIFY_DATA_FLOW_DISABLED', 'VERIFY_RESTORE_BLOCKED'],
         'The canonical operation order stops flows/restores before record deletion.'),
    ]
    for name, case, observations, status, operations, description in cases:
        import json
        assessment = assess_case(case, observations, RULES)
        row, _ = build_output(assessment)
        actual_ops = [step['operation'] for step in json.loads(row['steps_json'])]
        passed = row['deletion_status'] == status and actual_ops == operations
        results.append({'name': name, 'case_id': case['case_id'], 'description': description,
                        'expected_status': status, 'actual_status': row['deletion_status'],
                        'expected_operations': operations, 'actual_operations': actual_ops, 'passed': passed})
    return results
