"""Every async SDK operation must use one queue, including token counts/retries."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import ModelClient
from sdk_fakes import FakeSDK, response


class AsyncProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_cannot_retry_below_the_scheduler(self):
        import httpx
        from unittest.mock import AsyncMock
        calls = []
        async def network(request):
            calls.append(request)
            raise httpx.ConnectError('fixture disconnect', request=request)
        transport = httpx.MockTransport(network)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GEMINI_API_KEY': 'fixture-key',
                'GEMINI_TEXT_MODEL': 'fixture-model'}), \
             patch('llm.httpx.AsyncHTTPTransport', return_value=transport) as factory, \
             patch('google.genai._api_client.BaseApiClient._get_aiohttp_session',
                   new=AsyncMock(side_effect=AssertionError('SDK bypassed explicit transport'))):
            client = ModelClient(Path(temp)); client.max_retries = 0
            try:
                with self.assertLogs('audit', 'WARNING'):
                    self.assertIsNone(await client.request_json_async('fixture', 'fixture', {'type': 'ARRAY'}))
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(len(client.scheduler.history), 1)
                self.assertEqual(factory.call_args.kwargs['retries'], 0)
            finally:
                await client.aclose()

    async def test_shutdown_cancels_requests_sleeping_in_backoff(self):
        import threading
        from sdk_fakes import error
        original_sleep = asyncio.sleep; sleeping = threading.Event()
        async def observed_sleep(seconds):
            if seconds >= 30: sleeping.set()
            await original_sleep(seconds)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GEMINI_API_KEY': 'fixture-key',
                'GEMINI_TEXT_MODEL': 'fixture-model', 'GEMINI_RPM': '1000'}):
            sdk = FakeSDK(); sdk.models.generate_content.side_effect = error(503)
            with patch('llm.genai.Client', return_value=sdk), patch('llm.asyncio.sleep', side_effect=observed_sleep):
                client = ModelClient(Path(temp)); client.initial_delay = 30
                task = asyncio.create_task(client.request_json_async('fixture', 'fixture', {'type': 'ARRAY'}))
                self.assertTrue(await asyncio.to_thread(sleeping.wait, 1))
                await asyncio.wait_for(client.aclose(), 1)
                await original_sleep(0.01)
                self.assertTrue(task.done(), 'closing must resolve backoff requests before stopping their loop')
                result = await asyncio.gather(task, return_exceptions=True)
                self.assertIsInstance(result[0], asyncio.CancelledError)

    async def test_shared_sdk_queue_limits_concurrency_for_text_and_images(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'GEMINI_API_KEY': 'fixture-key', 'GEMINI_MODEL': 'gemini-3.6-flash',
                'GEMINI_TEXT_MODEL': '', 'GEMINI_VISION_MODEL': '',
                'GEMINI_RPM': '1000', 'GEMINI_TPM': '250000', 'GEMINI_MAX_CONCURRENCY': '2'}):
            sdk = FakeSDK(); active = peak = 0
            async def generate(**kwargs):
                nonlocal active, peak
                active += 1; peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1
                return response([])
            sdk.models.generate_content.side_effect = generate
            with patch('llm.genai.Client', return_value=sdk) as factory:
                client = ModelClient(Path(temp))
                try:
                    values = await asyncio.gather(*(client.request_json_async('fixture', f'prompt {i}', {'type': 'ARRAY'},
                                                                             image=b'image' if i % 2 else None) for i in range(6)))
                    self.assertEqual(values, [[]] * 6)
                    self.assertEqual(peak, 2)
                    self.assertEqual(client.scheduler.peak_concurrency, 2)
                    self.assertEqual(len(client.calls), 12)
                    self.assertEqual(len(client.scheduler.history), 12)
                    self.assertEqual(factory.call_count, 1)
                    self.assertEqual(factory.call_args.kwargs['http_options'].retry_options.attempts, 1)
                finally:
                    await asyncio.to_thread(client.close)
            self.assertEqual(client.text_model, 'gemini-3.6-flash')
            self.assertEqual(client.vision_model, 'gemini-3.6-flash')
            sdk.aclose.assert_awaited_once()

    async def test_invalid_quota_configuration_is_rejected(self):
        for name, value in [('GEMINI_RPM', '0'), ('GEMINI_TPM', '-1'), ('GEMINI_MAX_CONCURRENCY', 'no')]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {name: value}):
                with self.assertRaises(ValueError): ModelClient(Path(temp), offline=True)

    async def test_shutdown_cancels_queued_work_without_waiting_a_minute(self):
        import threading
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GEMINI_API_KEY': 'fixture-key',
                'GEMINI_TEXT_MODEL': 'fixture-model', 'GEMINI_RPM': '1'}):
            sdk = FakeSDK(); counted = threading.Event()
            async def count(**kwargs):
                counted.set(); return SimpleNamespace(total_tokens=10)
            sdk.models.count_tokens.side_effect = count
            with patch('llm.genai.Client', return_value=sdk):
                client = ModelClient(Path(temp))
                task = asyncio.create_task(client.request_json_async('fixture', 'fixture', {'type': 'ARRAY'}))
                self.assertTrue(await asyncio.to_thread(counted.wait, 1))
                await asyncio.sleep(0.01)
                await asyncio.wait_for(client.aclose(), 1)
                result = await asyncio.gather(task, return_exceptions=True)
                self.assertIsInstance(result[0], asyncio.CancelledError)
            sdk.models.generate_content.assert_not_awaited()
