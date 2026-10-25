"""Fictional regression cases derived from evidence-handling defects, not labels."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.fixtures import context,obs,RULES
from stage2 import category_for,parse_logs,EvidenceStore
from stage3 import assess_case,flow_risk,observed_state
from stage4 import build_output


class StateCalibrationTests(unittest.TestCase):
    def test_replica_activity_uses_canonical_business_service(self):
        self.assertEqual(category_for('', 'account_failover_replica',{},'account_demo'),('account_service','USER_PROFILE'))
        self.assertEqual(category_for('', 'account_replication_cluster',{},'account_demo'),('account_service','USER_PROFILE'))

    def test_marketing_lookup_purpose_overrides_analytics_resource_prefix(self):
        self.assertEqual(category_for('contact_lookup_completed','analytics_platform',{'email_opt_in':'true'},'analytics_demo'),
                         ('analytics_platform','MARKETING_PROFILE'))

    def test_partial_marker_read_does_not_erase_confirmed_record_presence(self):
        rows=[obs(resource='support_demo',system='support_platform',category='SUPPORT_ATTACHMENT',facts={'rows':1},when='2026-01-01T00:00:00Z'),
              obs(resource='support_demo',system='support_platform',category='SUPPORT_ATTACHMENT',facts={'event':'deletion_marker_check','marker_found':False},when='2026-01-01T00:00:01Z')]
        rules={**RULES,'SUPPORT_ATTACHMENT':{'rule_id':'fixture','required_action':'DELETE'}}
        resource=assess_case(context(),rows,rules)['resources'][0]
        self.assertEqual(resource['assessment'],'VIOLATION')
        self.assertEqual(resource['evidence_id'],'fixture-source')

    def test_later_idempotent_delete_claim_does_not_undermine_observed_absence(self):
        rows=[obs(facts={'rows':0}),obs(facts={'event_type':'DELETE_RECORD','reported_result':'SUCCESS'},kind='claim',when='2026-01-02T00:00:00Z')]
        self.assertEqual(assess_case(context(),rows,RULES)['resources'][0]['assessment'],'COMPLIANT')

    def test_subject_specific_connector_read_is_a_recreation_risk(self):
        case=context()
        for facts in [{'enabled':True,'lookup_key':'subject@example.test','event':'connector_heartbeat'},
                      {'result':'ACTIVE','subject_reference':'subject@example.test'}]:
            with self.subTest(facts=facts):
                row=obs(resource='connector-demo',system='integration_service',category='DATA_FLOW',facts=facts)
                self.assertTrue(flow_risk(row,[row],RULES,case))

    def test_bare_connector_without_subject_or_payload_scope_remains_unknown(self):
        row=obs(category='DATA_FLOW',facts={'enabled':True})
        self.assertIsNone(flow_risk(row,[row],RULES,context()))

    def test_structured_null_readback_is_not_exposed_pii(self):
        rows=parse_logs({'file_id':'fixture','captured_at':'2026-01-01T00:00:00Z'},
            '2026-01-01T00:00:00Z service=analytics_platform event=analytics_profile_read_completed resource_id=analytics_demo customer_reference=null email=null phone=null email_hash=null')
        self.assertEqual(observed_state(rows[0],context()),'ANONYMIZED')


class ScopeCalibrationTests(unittest.TestCase):
    def test_unread_image_with_observed_unrelated_identity_does_not_block_other_subject(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            store.failures=[{'file_id':'unrelated','captured_at':'2026-01-01T00:00:00Z',
                'scope_complete':True,'possible_identifiers':['other@example.test'],'possible_resources':['account_other']}]
            self.assertEqual(store.warnings_for(context()),[])

    def test_unread_matching_or_unscoped_image_keeps_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            for identifiers,complete in [(['subject@example.test'],True),([],False)]:
                store.failures=[{'file_id':'relevant','captured_at':'2026-01-01T00:00:00Z',
                    'scope_complete':complete,'possible_identifiers':identifiers,'possible_resources':[]}]
                self.assertTrue(store.warnings_for(context()))

class ScreenTextTests(unittest.TestCase):
    def test_malformed_low_confidence_neighbor_keeps_scope_unknown(self):
        from screen_ocr import assemble_screen
        regions=[[[[0,0],[90,0],[90,20],[0,20]],'other@example.test',.99],
                 [[[0,40],[90,40],[90,60],[0,60]],'subject@ exarnple.test',.40]]
        self.assertFalse(assemble_screen(regions)['scope_complete'])

    def test_no_resource_id_does_not_make_subject_artifact_successfully_empty(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            screen={'scope_complete':True,'possible_identifiers':['subject@example.test'],'possible_resources':[],
                    'possible_aliases':['private-support.png'],'primary_aliases':[],'text':'subject@example.test | private-support.png'}
            with patch('stage2.read_screen',return_value=screen):
                self.assertIsNone(store._parse({'file_id':'private'},Path('private.png'),b'fixture'))

    def test_ocr_lines_preserve_row_neighborhood_and_scope(self):
        from screen_ocr import assemble_screen
        regions=[[[[10,10],[90,10],[90,25],[10,25]],'account_demo',.99],
                 [[[100,10],[260,10],[260,25],[100,25]],'subject@example.test',.99],
                 [[[10,40],[90,40],[90,55],[10,55]],'account_other',.99]]
        screen=assemble_screen(regions)
        self.assertTrue(screen['scope_complete'])
        self.assertIn('subject@example.test',screen['possible_identifiers'])
        self.assertIn('account_demo',screen['possible_resources'])
        self.assertIn('account_demo | subject@example.test',screen['text'])

    def test_unreadable_image_cannot_claim_complete_scope(self):
        from screen_ocr import assemble_screen
        self.assertFalse(assemble_screen([])['scope_complete'])

    def test_placeholder_glyphs_are_not_positive_pii(self):
        from stage3 import exposed
        self.assertFalse(exposed({'email':'—','phone':'[removed]','name':'-','email_hash':None},'ACCOUNT_TOMBSTONE',context()))


class AliasScopeTests(unittest.TestCase):
    def test_visible_listing_owner_keeps_scoped_uncertainty_when_not_safely_attached(self):
        from unittest.mock import patch
        from stage2 import PartialExtraction
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            meta={'file_id':'listing','captured_at':'2026-01-01T00:00:00Z'}
            screen={'scope_complete':True,'possible_identifiers':['subject@example.test'],'possible_resources':[],
                'possible_aliases':['private.pdf'],'text':'Object Storage\nName | Owner Email | Size | Version\nprivate.pdf | subject@example.test | 2KB | v1'}
            with patch('stage2.read_screen',return_value=screen):
                with self.assertRaises(PartialExtraction):store._parse(meta,Path('screen.png'),b'fixture')
            store.failures=[meta]
            self.assertTrue(store.warnings_for(context()))
            other=context();other['identifiers']=['other@example.test']
            self.assertEqual(store.warnings_for(other),[])

    def test_conflicting_exclusive_catalog_owners_do_not_prove_deletable_attachment(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            store.by_alias['private.pdf']=[obs(resource='private.pdf',system='object_storage',category='',
                facts={'object_key':'private.pdf','record_exists':True},evidence='listing')]
            links=[obs(resource='object_demo',system='object_storage',category='',evidence='catalog-'+owner,
                facts={'event_type':'LINK_RESOURCE_IDENTITY','details':f'Attachment private.pdf belongs only to {owner}.'},kind='claim')
                for owner in ['subject@example.test','other@example.test']]
            store.activities=links
            store.by_identifier['subject@example.test']=[links[0]]
            store.by_resource['object_demo']=links
            self.assertFalse([row for row in store.retrieve(context()) if row.get('kind')!='claim'])

    def test_catalog_binding_uses_observed_object_not_operation_claim_as_state(self):
        from collections import defaultdict
        from common import eligible
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            source=obs(resource='private.pdf',system='object_storage',category='',
                facts={'object_key':'private.pdf','record_exists':True},evidence='actual-listing')
            link=obs(resource='object_demo',system='object_storage',category='',evidence='catalog-link',
                facts={'event_type':'LINK_RESOURCE_IDENTITY',
                'details':'Attachment catalog confirmed object_demo (private.pdf) belongs only to subject@example.test.'},kind='claim')
            link['identifiers']=['subject@example.test']
            store.activities=[link];store.by_alias['private.pdf']=[source]
            store.by_identifier['subject@example.test']=[link]
            store.by_resource['object_demo']=[link]
            found=[row for row in store.retrieve(context()) if row.get('kind')!='claim']
            self.assertEqual(len(found),1)
            self.assertEqual(found[0]['resource_id'],'object_demo')
            self.assertEqual(found[0]['evidence_id'],'actual-listing')
            self.assertEqual(found[0]['category'],'SUPPORT_ATTACHMENT')
            link['observed_at']=link['captured_at']='2026-03-01T00:00:00Z'
            self.assertEqual(store.retrieve(context()),[])

    def test_selected_alias_does_not_hide_unbound_neighbor(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            store.failures=[{'file_id':'screen','captured_at':'2026-01-01T00:00:00Z','scope_complete':True,
                'possible_identifiers':[],'possible_resources':[],'possible_aliases':['other.pdf','private.pdf'],
                'primary_aliases':['other.pdf']}]
            store.activities=[obs(resource='object_other',facts={'event_type':'LINK_RESOURCE_IDENTITY',
                'details':'Catalog linked other.pdf to other@example.test.'},kind='claim')]
            self.assertTrue(store.warnings_for(context()))

    def test_alias_binding_requires_exact_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            store.failures=[{'file_id':'screen','captured_at':'2026-01-01T00:00:00Z','scope_complete':True,
                'possible_identifiers':[],'possible_resources':[],'possible_aliases':['private.pdf']}]
            store.activities=[obs(resource='object_other',facts={'event_type':'LINK_RESOURCE_IDENTITY',
                'details':'Catalog linked not-private.pdf to other@example.test.'},kind='claim')]
            self.assertTrue(store.warnings_for(context()))

    def test_readable_storage_listing_preserves_all_objects_without_assuming_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            screen={'scope_complete':True,'possible_identifiers':[],'possible_resources':[],
                'possible_aliases':['other.pdf','private.pdf'],'primary_aliases':['other.pdf'],
                'text':'Object Storage\nName | Size | Version\nother.pdf | 1KB | v1\nprivate.pdf | 2KB | v1'}
            from unittest.mock import patch
            with patch('stage2.read_screen',return_value=screen):
                rows=store._parse({'file_id':'screen','captured_at':'2026-01-01T00:00:00Z'},Path('screen.png'),b'fixture')
            self.assertEqual({row['resource_id'] for row in rows},{'other.pdf','private.pdf'})
            self.assertTrue(all(not row['identifiers'] for row in rows))

    def test_catalog_filename_binding_scopes_failure_without_proving_state(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceStore(Path(temp),Mock(enabled=False),Path(temp)/'cache')
            meta={'file_id':'screen','captured_at':'2026-01-01T00:00:00Z','scope_complete':True,
                  'possible_identifiers':[],'possible_resources':[],'possible_aliases':['document.pdf'],
                  'primary_aliases':['document.pdf']}
            store.failures=[meta]
            self.assertTrue(store.warnings_for(context()),'unbound artifact remains unknown')
            link=obs(resource='object_demo',facts={'event_type':'LINK_RESOURCE_IDENTITY',
                'details':'Catalog linked document.pdf to other@example.test.'},kind='claim')
            store.activities=[link]
            self.assertEqual(store.warnings_for(context()),[])
            link['observed_at']=link['captured_at']='2026-03-01T00:00:00Z'
            self.assertTrue(store.warnings_for(context()),'future binding cannot exclude this subject')


class DeterminismTests(unittest.TestCase):
    def test_known_material_unknown_prevents_complete_even_with_compliant_profile(self):
        rows=[obs(facts={'rows':0}),obs(resource='archive-demo',system='backup_service',category='BACKUP_ARCHIVE',facts={})]
        self.assertEqual(build_output(assess_case(context(),rows,RULES))[0]['deletion_status'],'INCOMPLETE')

    def test_observation_order_does_not_change_status_or_steps(self):
        import random
        rows=[obs(facts={'resource_id':'profile-demo','email':'subject@example.test'}),
              obs(resource='archive-demo',system='backup_service',category='BACKUP_ARCHIVE',facts={'restore_allowed':True})]
        expected=build_output(assess_case(context(),rows,RULES))[0]
        for seed in range(10):
            shuffled=list(rows);random.Random(seed).shuffle(shuffled)
            self.assertEqual(build_output(assess_case(context(),shuffled,RULES))[0],expected)
