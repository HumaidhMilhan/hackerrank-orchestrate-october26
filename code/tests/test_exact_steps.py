"""General step-planning regressions; no public sample labels or IDs."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from evaluation.fixtures import context,obs,RULES
from stage1 import IdentityIndex
from stage2 import category_for,parse_logs
from stage3 import assess_case,flow_risk
from stage4 import build_output


class ExactStepTests(unittest.TestCase):
    def test_owned_email_identity_bridge_is_active_personal_data_flow(self):
        for selector in [{'customer_email':'subject@example.test'},{'lookup_key':'subject@example.test'}]:
            row=obs(resource='connector_demo',category='DATA_FLOW',system='integration_service',
                    facts={**selector,'enabled':True,'connector_name':'analytics_identity_bridge'})
            self.assertTrue(flow_risk(row,[row],RULES,context()))

    def test_subject_scoped_customer_events_connector_is_a_copy_path(self):
        row=obs(resource='connector_demo',category='DATA_FLOW',system='integration_service',
                facts={'customer_email':'subject@example.test','enabled':True,
                       'connector_name':'customer_events_connector','last_delivery_status':'delivered'})
        self.assertTrue(flow_risk(row,[row],RULES,context()))

    def test_explicit_retained_only_scope_overrides_connector_name(self):
        row=obs(category='DATA_FLOW',facts={'customer_email':'subject@example.test',
            'enabled':True,'connector_name':'analytics_identity_bridge','data_categories':['SECURITY_AUDIT_LOG']})
        self.assertFalse(flow_risk(row,[row],RULES,context()))

    def test_index_lookup_keeps_source_metadata_and_uses_identifier_policy(self):
        text=('2026-01-01T00:00:00Z service=support_replica trace_id=tr-demo event=contact_query_started '
              'lookup_key=subject@example.test source=legacy_contact_index\n'
              '2026-01-01T00:00:01Z service=support_replica trace_id=tr-demo event=contact_query_completed '
              'resource_id=support_demo rows=1')
        rows=parse_logs({'file_id':'fixture','captured_at':'2026-01-01T00:00:02Z'},text)
        self.assertEqual(rows[0]['facts'].get('source'),'legacy_contact_index')
        self.assertEqual(rows[0]['category'],'SECONDARY_IDENTIFIER')
        rules={**RULES,'SECONDARY_IDENTIFIER':{'rule_id':'fixture-index','required_action':'DELETE'}}
        output,_=build_output(assess_case(context(),rows,rules))
        self.assertEqual([s['operation'] for s in json.loads(output['steps_json'])],
                         ['REPORT_REMAINING_RECORD','DELETE_RECORD','VERIFY_RECORD_ABSENT'])

    def test_explicit_record_type_has_priority_over_contact_lookup_heuristic(self):
        self.assertEqual(category_for('contact_lookup_completed','support_platform',
            {'record_type':'SUPPORT_MESSAGE','email_opt_in':True},'support_demo')[1],'SUPPORT_MESSAGE')

    def test_claim_only_target_is_unknown_without_invented_action_plan_checks(self):
        rows=[obs(facts={'rows':0}),obs(resource='reference_demo',category='ACCOUNT_TOMBSTONE',
            facts={'event_type':'LINK_RESOURCE_IDENTITY'},kind='claim')]
        assessment=assess_case(context(),rows,RULES)
        output,_=build_output(assessment)
        self.assertEqual(output['deletion_status'],'INCOMPLETE')
        self.assertTrue(any(row['assessment']=='UNCERTAIN' for row in assessment['resources']))
        self.assertNotIn('reference_demo',output['steps_json'])

    def test_actual_worker_target_keeps_its_future_verification(self):
        rows=[obs(resource='account_demo',facts={'event_type':'DELETE_RECORD'},kind='claim')]
        output,_=build_output(assess_case(context(),rows,RULES))
        self.assertEqual(output['deletion_status'],'INCOMPLETE')
        self.assertEqual([s['operation'] for s in json.loads(output['steps_json'])],['VERIFY_RECORD_ABSENT'])

    def test_different_resource_absences_keep_independent_verification(self):
        case=context();case['requested_at']='2026-01-10T00:00:00Z'
        rows=[obs(resource='account_old',facts={'rows':0},when='2026-01-01T00:00:00Z'),
              obs(resource='account_current',facts={'rows':0},when='2026-01-15T00:00:00Z'),
              obs(resource='backup_demo',system='backup_service',category='BACKUP_ARCHIVE',facts={'restore_allowed':True})]
        output,_=build_output(assess_case(case,rows,RULES))
        self.assertEqual(output['deletion_status'],'INCOMPLETE')
        self.assertIn('account_old',output['steps_json'])
        self.assertIn('account_current',output['steps_json'])

    def test_new_read_on_reused_trace_does_not_inherit_business_type(self):
        text=('2026-01-01T00:00:00Z service=support_platform trace_id=tr-shared event=contact_query_started '
              'lookup_key=subject@example.test record_type=SECONDARY_IDENTIFIER source=legacy_contact_index\n'
              '2026-01-01T00:00:01Z service=support_platform trace_id=tr-shared event=contact_query_completed '
              'resource_id=secondary_demo rows=1\n'
              '2026-01-01T00:00:02Z service=support_platform trace_id=tr-shared event=support_message_read_started '
              'lookup_key=subject@example.test source=shared_conversations\n'
              '2026-01-01T00:00:03Z service=support_platform trace_id=tr-shared event=support_message_read_completed '
              'resource_id=support_demo rows=1 requester_email=subject@example.test')
        rows=parse_logs({'file_id':'fixture','captured_at':'2026-01-01T00:00:04Z'},text)
        self.assertEqual(rows[-1]['category'],'SUPPORT_MESSAGE')
        self.assertNotIn('record_type',rows[-1]['facts'])

    def test_old_absence_is_preserved_without_equivalent_current_check(self):
        case=context();case['requested_at']='2026-01-10T00:00:00Z'
        rows=[obs(resource='account_old',facts={'rows':0},when='2026-01-01T00:00:00Z'),
              obs(resource='backup_demo',system='backup_service',category='BACKUP_ARCHIVE',facts={'restore_allowed':True})]
        self.assertIn('account_old',build_output(assess_case(case,rows,RULES))[0]['steps_json'])

    def test_request_time_survives_identity_resolution(self):
        case={'case_id':'fixture','email':'subject@example.test','audit_at':'2026-02-01T00:00:00Z',
              'requested_at':'2026-01-10T00:00:00Z'}
        self.assertEqual(IdentityIndex([],[]).resolve(case,'DELETION').get('requested_at'),case['requested_at'])
