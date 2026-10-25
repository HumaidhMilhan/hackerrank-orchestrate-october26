"""Empty retrieval is unresolved coverage, never proof that records are absent."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.fixtures import context,obs,RULES
from stage2 import EvidenceStore
from stage3 import assess_case
from stage4 import build_output


class MissingEvidenceTests(unittest.TestCase):
    def test_authorized_request_with_no_linked_resources_has_uncertain_coverage(self):
        assessment=assess_case(context(),[],RULES)
        self.assertTrue(assessment['uncertain'])
        self.assertIn('No subject-linked state evidence at the audit cutoff.',assessment['warnings'])

    def test_no_data_fallback_explains_coverage_gap_without_inventing_checks(self):
        row,diagnostic=build_output(assess_case(context(),[],RULES))
        self.assertEqual(row['deletion_status'],'INCOMPLETE')
        self.assertEqual(row['steps_json'],'[]')
        self.assertEqual(diagnostic.get('reason_code'),'NO_SUBJECT_LINKED_STATE_EVIDENCE')

    def test_non_deletion_does_not_require_evidence_investigation(self):
        assessment=assess_case(context(intent='NON_DELETION'),[],RULES)
        self.assertFalse(assessment['uncertain'])
        self.assertEqual(build_output(assessment)[0]['deletion_status'],'NOT_APPLICABLE')

    def test_historical_resource_binding_reaches_later_anonymous_record(self):
        # This is the bridge an erased-identifier snapshot needs. Its absence
        # cannot be repaired by choosing an arbitrary anonymous row.
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            old=obs(resource='analytics_demo',system='analytics_platform',category='ANALYTICS_PROFILE',
                    facts={'resource_id':'analytics_demo','email':'subject@example.test'},evidence='old-owner')
            old['identifiers']=['subject@example.test']
            clean=obs(resource='analytics_demo',system='analytics_platform',category='ANALYTICS_PROFILE',
                      facts={'resource_id':'analytics_demo','user_id':None,'email':None,'phone':None,'email_hash':None},
                      evidence='later-anonymous',when='2026-01-02T00:00:00Z')
            clean['payload_complete']=True
            store.by_identifier['subject@example.test']=[old]
            store.by_resource['analytics_demo']=[old,clean]
            rules={**RULES,'ANALYTICS_PROFILE':{'rule_id':'fixture','required_action':'ANONYMIZE'}}
            found=store.retrieve(context())
            row,_=build_output(assess_case(context(),found,rules))
            self.assertEqual(row['deletion_status'],'COMPLETE')
            self.assertIn('later-anonymous',row['steps_json'])
            store.by_identifier.clear()
            self.assertEqual(store.retrieve(context()),[])
