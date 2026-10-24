"""Groq requests use the custom scheduler; all network traffic is mocked."""
import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import ModelClient

SCHEMA = {'type': 'ARRAY', 'items': {'type': 'OBJECT', 'properties': {
    'value': {'type': 'STRING'}}, 'required': ['value']}}


class GroqTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'AUDIT_PROVIDER': 'groq', 'GROQ_API_KEY': 'fixture',
            'GROQ_RPM': '1000', 'GROQ_TPM': '100000', 'GROQ_RPD': '1000', 'GROQ_TPD': '200000'})
        env.start(); self.addCleanup(env.stop)
        self.payloads = []; self.statuses = []
        self.finish_reason = 'stop'
        self.retry_after = '120'
        self.request_times = []
        async def network(request):
            self.request_times.append(time.monotonic())
            self.payloads.append(json.loads(request.content))
            status = self.statuses.pop(0) if self.statuses else 200
            if status != 200:
                return httpx.Response(status, json={'error': {'message': 'fixture'}}, request=request,
                                      headers={'retry-after': self.retry_after} if status == 429 else {})
            return httpx.Response(200, request=request, json={'id': 'fixture', 'object': 'chat.completion',
                'created': 0, 'model': self.payloads[-1]['model'], 'choices': [{'index': 0,
                'message': {'role': 'assistant', 'content': json.dumps({'items': [{'value': 'ok'}]})},
                'finish_reason': self.finish_reason}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
        self.transport = httpx.MockTransport(network)

    def client(self):
        from groq_client import GroqModelClient
        offline = ModelClient(Path(self.temp.name), offline=True)
        self.assertIsInstance(offline, GroqModelClient)
        offline.close()
        client = ModelClient(Path(self.temp.name)); self.addAsyncCleanup(client.aclose)
        return client

    async def test_routes_schema_image_usage_and_cache(self):
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client()
            self.assertEqual(await client.request_json_async('intent', 'request', SCHEMA), [{'value': 'ok'}])
            await client.request_json_async('intent_review', 'review', SCHEMA)
            await client.request_json_async('media', 'image', SCHEMA, image=b'fixture image')
            await client.request_json_async('intent', 'request', SCHEMA)
        self.assertEqual([p['model'] for p in self.payloads],
            ['openai/gpt-oss-20b', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b'])
        strict = self.payloads[0]['response_format']['json_schema']
        self.assertTrue(strict['strict'])
        self.assertFalse(strict['schema']['additionalProperties'])
        self.assertFalse(strict['schema']['properties']['items']['items']['additionalProperties'])
        self.assertEqual(self.payloads[2]['response_format'],{'type':'json_object'})
        self.assertEqual(self.payloads[2]['reasoning_effort'], 'none')
        self.assertEqual(self.payloads[2]['max_completion_tokens'], 512)
        self.assertTrue(self.payloads[2]['messages'][-1]['content'][-1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(client.cache_hits, 1)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(sum(x['input_tokens'] for x in client.calls), 30)
        self.assertEqual(sum(len(s.history) for s in client.schedulers.values()), 3)

    async def test_permanent_error_has_no_sdk_or_stage_retries(self):
        self.statuses = [403]
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client()
            self.assertIsNone(await client.request_json_async('intent', 'request', SCHEMA))
        self.assertFalse(client.retry_interpretation)
        self.assertEqual(len(self.payloads), 1)
        self.assertEqual(client.calls[0]['http_status'], 403)

    async def test_long_429_cools_only_affected_model(self):
        self.statuses = [429, 200]
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client()
            self.assertIsNone(await client.request_json_async('intent', 'request', SCHEMA))
            self.assertIsNone(await client.request_json_async('intent', 'request2', SCHEMA))
            self.assertIsNotNone(await client.request_json_async('intent_review', 'review', SCHEMA))
        self.assertEqual(len(self.payloads), 2)
        self.assertGreater(client.cooldown_until[client.text_model], 0)

    async def test_invalid_response_is_never_cached(self):
        def reject(_value): raise ValueError('fixture semantic rejection')
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client()
            for _ in range(2):
                self.assertIsNone(await client.request_json_async('intent', 'request', SCHEMA, validator=reject))
        self.assertEqual(len(self.payloads), 2)
        self.assertFalse(client.retry_interpretation)
        self.assertFalse(any(x['success'] for x in client.calls))

    async def test_shared_model_override_reuses_one_bucket(self):
        with patch.dict(os.environ, {'GROQ_REVIEW_MODEL': 'openai/gpt-oss-20b', 'GROQ_REVIEW_RPM': '7'}), \
             patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client()
            await client.request_json_async('intent', 'request', SCHEMA)
            await client.request_json_async('intent_review', 'review', SCHEMA)
        self.assertEqual(len(client.schedulers), 2)  # shared text/review, separate evidence
        self.assertEqual(len(client.schedulers[client.text_model].history), 2)
        self.assertEqual(client.schedulers[client.text_model].rpm, 7)

    async def test_transient_retry_returns_through_same_scheduler(self):
        self.statuses = [503, 200]
        from unittest.mock import AsyncMock
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport), \
             patch('groq_client.asyncio.sleep', new_callable=AsyncMock):
            client = self.client()
            self.assertIsNotNone(await client.request_json_async('intent', 'request', SCHEMA))
        self.assertEqual(len(self.payloads), 2)
        self.assertEqual(len(client.schedulers[client.text_model].history), 2)
        self.assertEqual([c['attempt'] for c in client.calls], [1,2])

    async def test_shutdown_cancels_groq_backoff_work(self):
        import threading
        started = threading.Event(); original_sleep = asyncio.sleep
        async def sleep(delay):
            started.set(); await original_sleep(30)
        self.statuses = [503]
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport), \
             patch('groq_client.asyncio.sleep', side_effect=sleep):
            client = self.client()
            task = asyncio.create_task(client.request_json_async('intent', 'request', SCHEMA))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            await asyncio.wait_for(client.aclose(), 1)
            result = await asyncio.gather(task, return_exceptions=True)
        self.assertIsInstance(result[0], asyncio.CancelledError)

    async def test_oversized_request_does_not_call_api(self):
        with patch.dict(os.environ, {'GROQ_TPM':'20'}), \
             patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client()
            self.assertIsNone(await client.request_json_async('intent', 'request', SCHEMA))
        self.assertFalse(self.payloads)
        self.assertFalse(client.retry_interpretation)

    async def test_truncated_response_is_rejected_and_not_cached(self):
        self.finish_reason = 'length'
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client()
            for _ in range(2):
                self.assertIsNone(await client.request_json_async('media', 'request', SCHEMA, image=b'image'))
        self.assertEqual(len(self.payloads),2)
        self.assertEqual(client.cache_hits,0)

    async def test_global_permit_precedes_model_quota_admission(self):
        import threading
        entered = threading.Event(); release = threading.Event()
        async def network(request):
            entered.set()
            while not release.is_set(): await asyncio.sleep(.01)
            return await self.transport.handle_async_request(request)
        with patch.dict(os.environ, {'GROQ_MAX_CONCURRENCY':'1'}), \
             patch('groq_client.httpx.AsyncHTTPTransport', return_value=httpx.MockTransport(network)):
            client = self.client()
            first = asyncio.create_task(client.request_json_async('intent','one',SCHEMA))
            self.assertTrue(await asyncio.to_thread(entered.wait,1))
            second = asyncio.create_task(client.request_json_async('intent_review','two',SCHEMA))
            await asyncio.sleep(.05)
            try:
                self.assertEqual(len(client.schedulers[client.intent_review_model].history),0,
                    'reservation must describe dispatch time, not time waiting for another model')
            finally:
                release.set()
                await asyncio.gather(first,second)

    async def test_invalid_configuration_and_provider_are_rejected(self):
        for name,value in [('GROQ_INTENT_CONFIDENCE','nan'),('GROQ_TPM','0'),
                           ('GROQ_MAX_CONCURRENCY','-1'),('AUDIT_PROVIDER','typo')]:
            with self.subTest(name=name), patch.dict(os.environ,{name:value}):
                with self.assertRaises(ValueError): ModelClient(Path(self.temp.name),offline=True)

    async def test_user_api_defaults_and_independent_model_buckets(self):
        with patch.dict(os.environ, {'GROQ_INTENT_CONFIDENCE':'', 'GROQ_INTENT_BATCH_SIZE':''}), \
             patch('groq_client.httpx.AsyncHTTPTransport',return_value=self.transport):
            client=self.client()
            self.assertEqual(client.intent_confidence_threshold,.80)
            self.assertEqual(client.intent_batch_size,4)
            await client.request_json_async('intent','one',SCHEMA)
            await client.request_json_async('media','image',SCHEMA,image=b'image')
            first=client.schedulers[client.text_model];vision=client.schedulers[client.vision_model]
            self.assertIsNot(first.window,vision.window)
            self.assertEqual(len(first.history),1)
            self.assertEqual(len(vision.history),1)

    async def test_local_value_error_does_not_replay_the_media_request(self):
        from stage2 import interpret_media
        with patch('groq_client.httpx.AsyncHTTPTransport',return_value=self.transport):
            client=self.client()
            result=await asyncio.to_thread(interpret_media,
                {'file_id':'fixture','captured_at':'2026-01-01T00:00:00Z'},client,b'image','fixture')
        self.assertIsNone(result)
        self.assertEqual(len(self.payloads),1)

    async def test_media_strict_schema_forbids_empty_resource_ids(self):
        from stage2 import MEDIA_SCHEMA
        with patch.dict(os.environ,{'GROQ_EVIDENCE_FORMAT':'strict'}),patch('groq_client.httpx.AsyncHTTPTransport',return_value=self.transport):
            client=self.client()
            await client.request_json_async('media','image',MEDIA_SCHEMA,image=b'image')
        schema=self.payloads[0]['response_format']['json_schema']['schema']
        resource=schema['properties']['items']['items']['properties']['resource_id']
        self.assertEqual(resource['minLength'],1)
        self.assertIn('pattern',resource)

    async def test_short_retry_after_is_shared_even_when_first_caller_exhausted(self):
        import time
        self.statuses = [429,200]; self.retry_after = '.15'
        with patch('groq_client.httpx.AsyncHTTPTransport', return_value=self.transport):
            client = self.client(); client.max_retries = 0
            self.assertIsNone(await client.request_json_async('intent','one',SCHEMA))
            start = time.monotonic()
            self.assertIsNotNone(await client.request_json_async('intent','two',SCHEMA))
            self.assertGreaterEqual(time.monotonic()-start,.13)

    async def test_queued_same_worker_observes_rate_limit_before_caller_wakes(self):
        self.statuses = [429,200]; self.retry_after = '.15'
        with patch.dict(os.environ,{'GROQ_MAX_CONCURRENCY':'1'}), \
             patch('groq_client.httpx.AsyncHTTPTransport',return_value=self.transport):
            client = self.client(); client.max_retries = 0
            await asyncio.gather(client.request_json_async('intent','one',SCHEMA),
                                 client.request_json_async('intent','two',SCHEMA))
        self.assertGreaterEqual(self.request_times[1]-self.request_times[0],.13)

    async def test_cancelled_caller_cannot_release_a_live_api_concurrency_slot(self):
        import threading
        entered = threading.Event(); release = threading.Event(); physical_calls = []
        async def network(request):
            physical_calls.append(request)
            entered.set()
            while not release.is_set(): await asyncio.sleep(.01)
            return await self.transport.handle_async_request(request)
        with patch.dict(os.environ,{'GROQ_MAX_CONCURRENCY':'1'}), \
             patch('groq_client.httpx.AsyncHTTPTransport',return_value=httpx.MockTransport(network)):
            client = self.client()
            first = asyncio.create_task(client.request_json_async('intent','one',SCHEMA))
            self.assertTrue(await asyncio.to_thread(entered.wait,1))
            first.cancel(); await asyncio.gather(first,return_exceptions=True)
            second = asyncio.create_task(client.request_json_async('intent_review','two',SCHEMA))
            await asyncio.sleep(.05)
            try:self.assertEqual(len(physical_calls),1,'physical slot must survive caller cancellation')
            finally:
                release.set(); await asyncio.gather(second,return_exceptions=True)


class LocalEvidenceRoutingTests(unittest.TestCase):
    def test_structured_and_text_evidence_never_calls_vision(self):
        from stage2 import EvidenceStore
        from unittest.mock import Mock
        client=Mock();client.request_json.side_effect=AssertionError('local evidence sent to vision')
        store=EvidenceStore(Path('.'),client,Path('.runtime/fixture'))
        meta={'file_id':'fixture','captured_at':'2026-01-01T00:00:00Z'}
        for extension,data in [('json',b'{}'),('sql',b'CREATE TABLE fixture (resource_id TEXT);'),
                               ('txt',b'ordinary handover'),('log',b'ordinary log')]:
            with self.subTest(extension=extension):store._parse(meta,Path('fixture.'+extension),data)
        client.request_json.assert_not_called()


class DailyQuotaTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_limits_survive_restart_and_expire(self):
        from quota import QuotaScheduler, DailyQuotaError
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'quota.json'; now = [100000.0]
            async def run(): return 1
            first = QuotaScheduler(100, 100, 1, rpd=1, tpd=20, ledger_path=path, wall_clock=lambda: now[0])
            await first.call(run, tokens=10); await first.aclose()
            second = QuotaScheduler(100, 100, 1, rpd=1, tpd=20, ledger_path=path, wall_clock=lambda: now[0])
            with self.assertRaises(DailyQuotaError): await second.call(run, tokens=1)
            now[0] += 86401
            self.assertEqual(await second.call(run, tokens=1), 1)
            await second.aclose()

    async def test_daily_token_limit_keeps_failed_reservations(self):
        from quota import QuotaScheduler, DailyQuotaError
        scheduler = QuotaScheduler(100, 100, 1, rpd=100, tpd=10)
        self.addAsyncCleanup(scheduler.aclose)
        async def fail(): raise TimeoutError()
        with self.assertRaises(TimeoutError): await scheduler.call(fail, tokens=8)
        with self.assertRaises(DailyQuotaError): await scheduler.call(fail, tokens=3)

    async def test_corrupt_ledger_fails_closed_without_network(self):
        from quota import QuotaScheduler, DailyQuotaError
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'quota.json'
            for content in ['invalid', '{"reservations":{}}',
                '{"reservations":[{"wall_at":NaN,"tokens":1,"operation":"intent"}]}',
                '{"reservations":[{"wall_at":1,"tokens":1,"minute_tokens":"bad","operation":"intent"}]}']:
                with self.subTest(content=content):
                    path.write_text(content, encoding='utf-8')
                    scheduler = QuotaScheduler(100,100,1,rpd=100,tpd=100,ledger_path=path)
                    self.addAsyncCleanup(scheduler.aclose)
                    async def fail(): self.fail('untracked network dispatch')
                    with self.assertRaises(DailyQuotaError): await scheduler.call(fail, tokens=1)

    async def test_success_settles_daily_usage_but_keeps_minute_reservation(self):
        from quota import QuotaScheduler
        scheduler = QuotaScheduler(100,100,1,rpd=100,tpd=50,settle_daily=True)
        self.addAsyncCleanup(scheduler.aclose)
        async def run(): return 10
        await scheduler.call(run,tokens=40,actual_tokens=lambda x:x)
        await scheduler.call(run,tokens=40,actual_tokens=lambda x:x)
        self.assertEqual(sum(x['tokens'] for x in scheduler.day_window),20)
        self.assertEqual(sum(x['tokens'] for x in scheduler.window),80)


class UsageTests(unittest.TestCase):
    def test_escalation_calls_have_explicit_task_totals(self):
        from main import usage_summary
        calls=[dict(provider='groq',model='shared',task=t,input_tokens=1,output_tokens=1)
               for t in ['intent','intent_review','intent_review','media']]
        summary=usage_summary(calls,0,2,'evaluation','fixture')
        self.assertEqual(summary['task_counts'],{'intent':1,'intent_review':2,'media':1})

    def test_groq_costs_are_per_model_and_reasoning_is_not_added_twice(self):
        from main import usage_summary
        calls = [dict(provider='groq', model=model, input_tokens=1000, output_tokens=200,
                      thinking_tokens=0, reasoning_tokens_in_output=50, cached_tokens=0)
                 for model in ['openai/gpt-oss-20b','openai/gpt-oss-120b']]
        env = {'AUDIT_INPUT_USD_PER_MILLION':'99','AUDIT_OUTPUT_USD_PER_MILLION':'99',
               'GROQ_INTENT_INPUT_USD_PER_MILLION':'2','GROQ_INTENT_OUTPUT_USD_PER_MILLION':'4',
               'GROQ_REVIEW_INPUT_USD_PER_MILLION':'10','GROQ_REVIEW_OUTPUT_USD_PER_MILLION':'20'}
        with patch.dict(os.environ, env): summary = usage_summary(calls, 0, 2, 'evaluation', 'fixture')
        self.assertAlmostEqual(summary['overall']['estimated_usd'], .0168)
        self.assertEqual(summary['overall']['total_tokens'], 2400)
