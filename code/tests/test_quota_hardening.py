"""Quota reconciliation, configuration and observer-failure regressions."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quota import QuotaScheduler
from test_quota import Clock


class ReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_learned_provider_limit_bounds_aggregate_after_reset(self):
        clock=Clock();scheduler=QuotaScheduler(100,8000,1,clock=clock,sleep=clock.sleep,settle_minute=True)
        self.addAsyncCleanup(scheduler.aclose)
        async def small():return 10
        await scheduler.call(small,tokens=10,actual_tokens=lambda x:x,rate_headers=lambda _:{
            'x-ratelimit-limit-tokens':'1000','x-ratelimit-remaining-tokens':'990','x-ratelimit-reset-tokens':'1s'})
        clock.now=61;starts=[]
        async def big():starts.append(clock());return 900
        for _ in range(2):await scheduler.call(big,tokens=900,actual_tokens=lambda x:x)
        self.assertEqual(starts,[61,121])

    async def test_header_debt_does_not_mint_tokens_when_inflight_work_settles(self):
        scheduler=QuotaScheduler(100,8000,2,settle_minute=True)
        self.addAsyncCleanup(scheduler.aclose)
        started=asyncio.Event();release=asyncio.Event()
        async def slow():started.set();await release.wait();return 100
        task=asyncio.create_task(scheduler.call(slow,tokens=3000,actual_tokens=lambda x:x))
        await started.wait()
        async def fast():return 1
        await scheduler.call(fast,tokens=1,actual_tokens=lambda x:x,rate_headers=lambda _:{
            'x-ratelimit-remaining-tokens':'50','x-ratelimit-reset-tokens':'60s'})
        release.set();await task
        self.assertLessEqual(scheduler.provider_remaining,50)

    async def test_usage_reconciliation_wakes_waiting_admission(self):
        scheduler=QuotaScheduler(100,100,2,settle_minute=True)
        self.addAsyncCleanup(scheduler.aclose)
        started=asyncio.Event();release=asyncio.Event()
        async def first():started.set();await release.wait();return 10
        async def second():return 10
        a=asyncio.create_task(scheduler.call(first,tokens=80,actual_tokens=lambda x:x))
        await started.wait()
        b=asyncio.create_task(scheduler.call(second,tokens=80,actual_tokens=lambda x:x))
        await asyncio.sleep(.02);release.set()
        await asyncio.wait_for(asyncio.gather(a,b),.5)

    async def test_lower_provider_limit_is_preserved_after_reset(self):
        from quota import QuotaCapacityError
        clock=Clock();scheduler=QuotaScheduler(100,8000,1,clock=clock,sleep=clock.sleep,settle_minute=True)
        self.addAsyncCleanup(scheduler.aclose)
        async def response():return 10
        await scheduler.call(response,tokens=10,actual_tokens=lambda x:x,rate_headers=lambda _:{
            'x-ratelimit-limit-tokens':'1000','x-ratelimit-remaining-tokens':'990','x-ratelimit-reset-tokens':'1s'})
        clock.now=2
        with self.assertRaises(QuotaCapacityError):await scheduler.call(response,tokens=2000)

    async def test_known_usage_releases_minute_reservation(self):
        clock=Clock();scheduler=QuotaScheduler(100,8000,1,clock=clock,sleep=clock.sleep,settle_minute=True)
        self.addAsyncCleanup(scheduler.aclose)
        async def response():return 2200
        await scheduler.call(response,tokens=5144,actual_tokens=lambda x:x)
        await scheduler.call(response,tokens=5144,actual_tokens=lambda x:x)
        self.assertEqual(clock(),0)
        self.assertEqual(sum(x['tokens'] for x in scheduler.window),4400)

    async def test_header_headroom_and_reset_bound_admission(self):
        clock=Clock();scheduler=QuotaScheduler(100,8000,1,clock=clock,sleep=clock.sleep,settle_minute=True)
        self.addAsyncCleanup(scheduler.aclose)
        async def response():return 100
        headers={'x-ratelimit-limit-tokens':'8000','x-ratelimit-remaining-tokens':'50',
                 'x-ratelimit-reset-tokens':'2s','x-ratelimit-limit-requests':'1000'}
        await scheduler.call(response,tokens=100,actual_tokens=lambda x:x,rate_headers=lambda _:headers)
        await scheduler.call(response,tokens=100,actual_tokens=lambda x:x)
        self.assertEqual(clock(),2)
        self.assertEqual(scheduler.rpm,100,'request headers describe RPD, not RPM')

    async def test_header_snapshot_deducts_other_inflight_reservations(self):
        scheduler=QuotaScheduler(100,8000,2,settle_minute=True)
        self.addAsyncCleanup(scheduler.aclose)
        release=asyncio.Event();started=asyncio.Event()
        async def slow():started.set();await release.wait();return 100
        slow_task=asyncio.create_task(scheduler.call(slow,tokens=3000,actual_tokens=lambda x:x))
        await started.wait()
        async def fast():return 100
        await scheduler.call(fast,tokens=100,actual_tokens=lambda x:x,rate_headers=lambda _:{
            'x-ratelimit-remaining-tokens':'7000','x-ratelimit-reset-tokens':'60s'})
        self.assertLessEqual(scheduler.provider_remaining,4000)
        release.set();await slow_task


class ConfigurationTests(unittest.TestCase):
    def test_requested_caps_formats_and_retry_budget(self):
        from llm import ModelClient
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'AUDIT_PROVIDER':'groq'},clear=True):
            client=ModelClient(Path(temp),offline=True)
            try:
                self.assertEqual(client.intent_batch_size,4)
                self.assertEqual(client.role_config['INTENT']['max_output_tokens'],512)
                self.assertEqual(client.role_config['REVIEW']['max_output_tokens'],512)
                self.assertEqual(client.role_config['EVIDENCE']['format'],'json')
                self.assertEqual(client.max_retries,1)
            finally:client.close()

    def test_env_last_definition_wins_but_external_environment_wins(self):
        from llm import load_env
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'KEEP_FIXTURE':'external'},clear=True):
            path=Path(temp)/'.env';path.write_text('CAP_FIXTURE=1024\nCAP_FIXTURE=256\nKEEP_FIXTURE=file\n')
            load_env(path)
            self.assertEqual(os.environ['CAP_FIXTURE'],'256')
            self.assertEqual(os.environ['KEEP_FIXTURE'],'external')

    def test_diagnostics_report_schema_path_without_value(self):
        from groq_client import validate_schema
        try:validate_schema({'items':[{'number':'sensitive-content'}]}, {'type':'object','properties':{
            'items':{'type':'array','items':{'type':'object','properties':{'number':{'type':'number'}}}}}})
        except ValueError as error:
            self.assertEqual(error.path,'$.items[0].number')
            self.assertNotIn('sensitive-content',str(error))
        else:self.fail('invalid data accepted')

    def test_redacted_body_diagnostics_preserve_shape_without_contents(self):
        from api_diagnostics import redacted_body
        data={'choices':[{'message':{'content':json.dumps({'items':[{'phone':14155552671,'email':'person@example.test',
            'supporting_text':'Secret person name','facts_json':'{"name":"Real name"}'}]})}}]}
        rendered=json.dumps(redacted_body(data))
        for value in ['14155552671','person@example.test','Secret person name','Real name']:
            self.assertNotIn(value,rendered)
        self.assertIn('items',rendered)

    def test_response_object_keys_cannot_leak_private_values(self):
        from api_diagnostics import redacted_body
        body={'choices':[{'message':{'content':json.dumps({'items':[{'facts_json':json.dumps({
            'person@example.test':'value','PrivatePersonName':'value','gsk_secret_fixture':'value'})}]})}}]}
        rendered=json.dumps(redacted_body(body))
        for value in ['person@example.test','PrivatePersonName','gsk_secret_fixture']:self.assertNotIn(value,rendered)


class ObserverFailureTests(unittest.TestCase):
    def test_failed_targeted_recheck_preserves_facts_and_blocks_completion(self):
        from unittest.mock import Mock
        from stage2 import EvidenceStore
        from stage3 import assess_case
        from stage4 import build_output
        from evaluation.fixtures import context,obs,RULES
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'visual.png').write_bytes(b'fixture')
            store=EvidenceStore(root,Mock(enabled=True),root/'cache')
            meta={'file_id':'visual','file_path':'visual.png','captured_at':'2026-01-01T00:00:00Z'}
            store.artifacts={'visual':meta}
            original=[obs(facts={'rows':0},evidence='visual'),obs(resource='profile-other',facts={},evidence='visual')]
            store.retrieve=Mock(return_value=list(original))
            with patch('stage2.interpret_media',return_value=None):refreshed=store.recheck(context(),original)
            self.assertEqual(refreshed,original)
            assessment=assess_case(context(),refreshed,RULES,store.warnings_for(context()))
            self.assertTrue(assessment['observation_failure'])
            self.assertEqual(build_output(assessment)[0]['deletion_status'],'INCOMPLETE')
    def test_failed_observer_cannot_produce_complete_or_invent_findings(self):
        from stage3 import assess_case
        from stage4 import build_output
        from evaluation.fixtures import context,obs,RULES
        assessment=assess_case(context(),[obs(facts={'rows':0})],RULES,['visual extraction failed'])
        row,diagnostic=build_output(assessment)
        self.assertEqual(assessment['resources'][0]['assessment'],'COMPLIANT')
        self.assertEqual(row['deletion_status'],'INCOMPLETE')
        self.assertFalse(any(s['phase']=='FINDING' for s in json.loads(row['steps_json'])))
        self.assertTrue(diagnostic['estimated'])
