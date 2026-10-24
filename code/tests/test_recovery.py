"""Confirmed quota lifecycle and protocol recovery, without live APIs."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class ConfirmedUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'usage.json'
        self.now=[datetime(2026,10,25,tzinfo=timezone.utc).timestamp()]

    def ledger(self):
        from daily_usage import DailyUsageLedger
        return DailyUsageLedger(self.path,clock=lambda:self.now[0])

    def test_estimate_is_temporary_and_only_actual_is_persisted(self):
        ledger=self.ledger();reservation=ledger.reserve('model-a',5000,1000,200000)
        self.assertEqual(ledger.snapshot('model-a')['inflight_reserved_tokens'],5000)
        ledger.record_response('model-a',1300)
        ledger.release(reservation)
        state=json.loads(self.path.read_text())
        self.assertEqual(state['models']['model-a']['tokens_today'],1300)
        self.assertEqual(state['models']['model-a']['requests_today'],1)
        self.assertNotIn('reservations',state)
        self.assertNotIn('5000',self.path.read_text())

    def test_local_skip_does_not_count_as_provider_usage(self):
        from quota import DailyQuotaError
        ledger=self.ledger();ledger.record_response('model-a',10)
        with self.assertRaises(DailyQuotaError):ledger.reserve('model-a',100,1,1000)
        self.assertEqual(ledger.snapshot('model-a')['requests_today'],1)
        self.assertEqual(ledger.snapshot('model-a')['tokens_today'],10)

    def test_models_are_separate_and_yesterday_resets_in_utc(self):
        ledger=self.ledger();ledger.record_response('model-a',190000)
        token=ledger.reserve('model-b',5000,1000,200000);ledger.release(token)
        self.now[0]+=86400
        self.assertEqual(self.ledger().snapshot('model-a')['tokens_today'],0)
        self.assertEqual(self.ledger().snapshot('model-a')['date'],'2026-10-26')

    def test_unknown_response_usage_is_not_invented_as_tokens(self):
        ledger=self.ledger();ledger.record_response('model-a',None)
        snapshot=ledger.snapshot('model-a')
        self.assertEqual(snapshot['requests_today'],1)
        self.assertEqual(snapshot['tokens_today'],0)
        self.assertEqual(snapshot['unknown_usage_calls'],1)


class PrimaryRecoveryTests(unittest.TestCase):
    def test_truncated_batch_splits_primary_without_semantic_review(self):
        from stage1 import interpret_requests
        class Client:
            enabled=True;intent_review_model='secondary';intent_confidence_threshold=.8;intent_batch_size=4
            retry_interpretation=False;last_outcome={'reason':'accepted'}
            def __init__(self):self.tasks=[]
            def request_json(self,task,prompt,schema,validator=None,**kwargs):
                self.tasks.append(task)
                data=json.loads(prompt[prompt.index('[{'):])
                if len(self.tasks)==1:self.last_outcome={'reason':'truncated'};return None
                self.last_outcome={'reason':'accepted'}
                return [{'case_id':r['case_id'],'intent':'DELETION','confidence':.99,
                         'supporting_phrase':'Delete my account'} for r in data]
        client=Client();requests=[{'case_id':str(i),'request_text':'Delete my account'} for i in range(4)]
        result=interpret_requests(requests,client)
        self.assertEqual(client.tasks,['intent','intent','intent'])
        self.assertTrue(all(x['intent']=='DELETION' for x in result.values()))
        self.assertTrue(all('primary_truncated' in x['recovery_reasons'] for x in result.values()))

    def test_primary_api_failure_never_becomes_semantic_review(self):
        from stage1 import interpret_requests
        class Client:
            enabled=True;intent_review_model='secondary';intent_confidence_threshold=.8;intent_batch_size=4
            retry_interpretation=False;last_outcome={'reason':'api_failure'}
            def __init__(self):self.tasks=[]
            def request_json(self,task,*args,**kwargs):self.tasks.append(task);return None
        client=Client();result=interpret_requests([{'case_id':'x','request_text':'Delete my account'}],client)
        self.assertEqual(client.tasks,['intent'])
        self.assertEqual(result['x']['resolution_reason'],'primary_api_failure')


class NativeObservationTests(unittest.TestCase):
    def test_native_envelope_converts_structured_facts_without_verdict(self):
        from visual_observer import parse_visual
        response={'observations':[{'fact':'{"resource_id":"account_demo","record_type":"USER_PROFILE","email":"a@example.test"}',
             'source_reference':'selected profile','confidence':.99}], 'ambiguities':[],'missing_information':[]}
        rows,incomplete=parse_visual(response)
        self.assertFalse(incomplete)
        self.assertEqual(rows[0]['resource_id'],'account_demo')
        self.assertEqual(json.loads(rows[0]['facts_json'])['email'],'a@example.test')
        self.assertNotIn('deletion_status',rows[0])

    def test_repair_guard_rejects_facts_absent_from_source_text(self):
        from visual_observer import validate_repair
        source='{"observations":[{"fact":"visible record", "source_reference":"row 1","confidence":0.9}]'
        with self.assertRaises(ValueError):validate_repair({'observations':[{'fact':'invented deleted record',
             'source_reference':'row 1','confidence':.9}],'ambiguities':[],'missing_information':[]},source)

class ProviderRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_vision_is_repaired_once_without_resending_image(self):
        import httpx
        from llm import ModelClient
        from stage2 import MEDIA_SCHEMA
        with tempfile.TemporaryDirectory() as temp:
            payloads=[]
            fact='resource_id=account_demo;email=a@example.test'
            malformed=json.dumps({'observations':[{'fact':fact,'source_reference':'row 1','confidence':.99}],
                                  'ambiguities':[],'missing_information':[]})[:-1]
            async def network(request):
                payload=json.loads(request.content);payloads.append(payload)
                content=(malformed if len(payloads)==1 else json.dumps({'items':{
                    'observations':[{'fact':fact,'source_reference':'row 1','confidence':.99}],
                    'ambiguities':[],'missing_information':[]}}))
                return httpx.Response(200,request=request,json={'id':'fixture','object':'chat.completion','created':0,
                    'model':payload['model'],'choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}})
            with patch.dict(os.environ,{'AUDIT_PROVIDER':'groq','GROQ_API_KEY':'fixture','GROQ_TPM':'100000'}),patch(
                'groq_client.httpx.AsyncHTTPTransport',return_value=httpx.MockTransport(network)):
                client=ModelClient(Path(temp))
                try:rows=await client.request_json_async('media','image',MEDIA_SCHEMA,image=b'image')
                finally:await client.aclose()
            self.assertEqual(rows[0]['resource_id'],'account_demo')
            self.assertEqual(len(payloads),2)
            self.assertEqual(payloads[1]['model'],'openai/gpt-oss-20b')
            self.assertNotIn('image_url',json.dumps(payloads[1]))
            self.assertEqual(client.daily_usage.snapshot(client.vision_model)['tokens_today'],130)
            self.assertEqual(client.daily_usage.snapshot(client.text_model)['tokens_today'],130)
            self.assertEqual(client.calls[0]['recovered_via'],'text_repair')

    async def test_actual_usage_is_recorded_for_truncated_response_and_local_skip_not_attempted(self):
        import httpx
        from llm import ModelClient
        from main import usage_summary
        schema={'type':'ARRAY','items':{'type':'STRING'}}
        with tempfile.TemporaryDirectory() as temp:
            async def network(request):
                return httpx.Response(200,request=request,json={'id':'fixture','object':'chat.completion','created':0,
                    'model':'openai/gpt-oss-20b','choices':[{'index':0,'message':{'role':'assistant','content':'{'},'finish_reason':'length'}],
                    'usage':{'prompt_tokens':1000,'completion_tokens':300,'total_tokens':1300}})
            with patch.dict(os.environ,{'AUDIT_PROVIDER':'groq','GROQ_API_KEY':'fixture','GROQ_RPD':'1','GROQ_TPM':'100000'}),patch(
                'groq_client.httpx.AsyncHTTPTransport',return_value=httpx.MockTransport(network)):
                client=ModelClient(Path(temp))
                try:
                    self.assertIsNone(await client.request_json_async('intent','test',schema))
                    self.assertEqual(client.last_outcome['reason'],'truncated')
                    self.assertIsNone(await client.request_json_async('intent','test again',schema))
                finally:await client.aclose()
            state=client.daily_usage.snapshot(client.text_model)
            self.assertEqual((state['requests_today'],state['tokens_today'],state['inflight_reserved_tokens']),(1,1300,0))
            stats=usage_summary(client.calls,0,1,'test','fixture',client.events)['overall']
            self.assertEqual(stats['attempted_calls'],1)
            self.assertEqual(stats['local_quota_skips'],1)
            self.assertEqual(stats['truncated_calls'],1)
            self.assertEqual(stats['actual_tokens'],1300)


class MigrationTests(unittest.TestCase):
    def test_legacy_estimates_are_archived_and_only_proven_actual_migrates(self):
        from common import digest
        from daily_usage import DailyUsageLedger
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);legacy=root/'groq_quotas';legacy.mkdir()
            now=datetime(2026,10,25,tzinfo=timezone.utc).timestamp()
            (legacy/(digest('model')+'.json')).write_text(json.dumps({'reservations':[
                {'wall_at':now,'tokens':5000,'minute_tokens':5000},
                {'wall_at':now,'tokens':1300,'minute_tokens':5000},
                {'wall_at':now-86400,'tokens':9999,'minute_tokens':5000}]}))
            ledger=DailyUsageLedger(root/'usage.json',clock=lambda:now,legacy_dir=legacy,models=['model'])
            self.assertEqual(ledger.snapshot('model')['tokens_today'],1300)
            self.assertEqual(ledger.snapshot('model')['requests_today'],1)
            self.assertEqual(len(list((root/'groq_quota_archive').rglob('*.json'))),1)

    def test_malformed_saved_date_fails_closed_without_crashing(self):
        from daily_usage import DailyUsageLedger
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'usage.json';path.write_text('{"models":{}}')
            ledger=DailyUsageLedger(path)
            self.assertTrue(ledger.snapshot('model')['state_unavailable'])

class MediaAdapterTests(unittest.TestCase):
    def test_category_uses_existing_grounded_resource_mapping_when_not_printed(self):
        from stage2 import media_rows
        rows=media_rows({'file_id':'fixture','captured_at':'2026-01-01T00:00:00Z'},[{
            'resource_id':'account_demo','system_id':'','record_type':'',
            'facts_json':'{"email":"a@example.test"}','supporting_text':'row 1'}],'fixture')
        self.assertEqual(rows[0]['category'],'USER_PROFILE')
        self.assertEqual(rows[0]['system_id'],'account_service')

    def test_compact_key_value_facts_remain_observations(self):
        from visual_observer import parse_visual
        value={'observations':[{'fact':'resource_id=data_flow_demo;active=false;email=a@example.test',
            'source_reference':'row 1','confidence':.99}],'ambiguities':[],'missing_information':[]}
        rows,incomplete=parse_visual(value)
        self.assertFalse(incomplete)
        self.assertIs(json.loads(rows[0]['facts_json'])['active'],False)

class LedgerIntegrityTests(unittest.TestCase):
    def test_invalid_model_counters_fail_closed_without_stopping_the_runner(self):
        from daily_usage import DailyUsageLedger
        for counters in [[],{'requests_today':1,'tokens_today':10,'cached_tokens_today':20,'unknown_usage_calls':0}]:
            with self.subTest(counters=counters),tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'usage.json'
                path.write_text(json.dumps({'date':datetime.now(timezone.utc).date().isoformat(),'timezone':'UTC','models':{'model':counters}}))
                self.assertTrue(DailyUsageLedger(path).snapshot('model')['state_unavailable'])
