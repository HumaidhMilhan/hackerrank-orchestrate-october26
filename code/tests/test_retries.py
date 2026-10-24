"""Transport backoff stays bounded and every SDK retry uses the quota queue."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import ModelClient
from sdk_fakes import FakeSDK, error, response


class RetryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict('os.environ', {'GEMINI_API_KEY': 'fixture-key', 'GEMINI_TEXT_MODEL': 'fixture-model', 'GEMINI_RPM': '1000'})
        env.start(); self.addCleanup(env.stop)
        self.sdk = FakeSDK()
        sdk = patch('llm.genai.Client', return_value=self.sdk)
        sdk.start(); self.addCleanup(sdk.stop)
        self.client = ModelClient(Path(temp.name)); self.addCleanup(self.client.close)

    def test_transient_errors_back_off_with_jitter_and_count_every_call(self):
        self.sdk.models.generate_content.side_effect = [error(503), error(408), httpx.ConnectError('fixture'), TimeoutError(), response([])]
        with patch('llm.asyncio.sleep', new_callable=AsyncMock) as sleep, patch('llm.random.uniform', return_value=0.2):
            with self.assertLogs('audit', 'WARNING'):
                self.assertEqual(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}), [])
        self.assertEqual(self.sdk.models.generate_content.call_count, 5)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [1.2, 2.2, 4.2, 8.2])
        self.assertEqual(len(self.client.calls), 6)  # token count plus all physical generation attempts
        self.assertEqual(len(self.client.scheduler.history), 6)
        self.assertEqual(self.client.calls[-1]['input_tokens'], 11)

    def test_transport_exhaustion_does_not_get_an_extra_stage1_retry(self):
        from stage1 import interpret_requests
        self.sdk.models.generate_content.side_effect = error(503)
        with patch('llm.asyncio.sleep', new_callable=AsyncMock):
            with self.assertLogs('audit', 'WARNING'):
                result = interpret_requests([{'case_id': 'demo', 'request_text': 'Delete my account.'}], self.client)
        self.assertEqual(self.sdk.models.generate_content.call_count, 5)
        self.assertEqual(result['demo']['method'], 'rules')

    def test_permanent_errors_are_not_retried_by_transport_or_stages(self):
        from stage1 import interpret_requests
        from stage2 import interpret_media
        for code in [400, 402, 403, 404]:
            self.sdk.models.generate_content.reset_mock(side_effect=True)
            self.sdk.models.generate_content.side_effect = error(code)
            with self.subTest(code=code), patch('llm.asyncio.sleep', new_callable=AsyncMock) as sleep:
                with self.assertLogs('audit', 'WARNING'):
                    result = interpret_requests([{'case_id': 'demo', 'request_text': 'Delete my account.'}], self.client)
                self.assertEqual(result['demo']['method'], 'rules')
                self.assertEqual(self.sdk.models.generate_content.call_count, 1)
                sleep.assert_not_awaited()
        self.sdk.models.generate_content.reset_mock(side_effect=True)
        self.sdk.models.generate_content.side_effect = error(403)
        with self.assertLogs('audit', 'WARNING'):
            self.assertIsNone(interpret_media({'file_id': 'fixture', 'captured_at': '2026-01-01T00:00:00Z'},
                                            self.client, b'fixture-image', 'fixture'))
        self.assertEqual(self.sdk.models.generate_content.call_count, 1)

    def test_invalid_interpretation_uses_one_repair_without_transport_sleep(self):
        from stage1 import interpret_requests
        def intent(phrase): return response([{'case_id': 'demo', 'intent': 'DELETION', 'supporting_phrase': phrase}])
        self.sdk.models.generate_content.side_effect = [intent('invented'), intent('Delete my account')]
        with patch('llm.asyncio.sleep', new_callable=AsyncMock) as sleep:
            with self.assertLogs('audit', 'WARNING'):
                result = interpret_requests([{'case_id': 'demo', 'request_text': 'Delete my account.'}], self.client)
        self.assertEqual(self.sdk.models.generate_content.call_count, 2)
        self.assertEqual(self.sdk.models.count_tokens.call_count, 1)
        self.assertEqual(result['demo']['method'], 'model')
        sleep.assert_not_awaited()

    def test_retry_after_header_is_respected(self):
        self.sdk.models.generate_content.side_effect = [error(429, {'Retry-After': '3'}), response([])]
        with patch('llm.asyncio.sleep', new_callable=AsyncMock) as sleep, patch('llm.random.uniform', return_value=0):
            with self.assertLogs('audit', 'WARNING'):
                self.assertEqual(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}), [])
        sleep.assert_awaited_once_with(3.0)

    def test_long_google_retry_delay_defers_same_model_without_sleeping_hours(self):
        body = {'error': {'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '3600s'}]}}
        self.sdk.models.generate_content.side_effect = error(429, body=body)
        with patch('llm.asyncio.sleep', new_callable=AsyncMock) as sleep:
            with self.assertLogs('audit', 'WARNING'):
                self.assertIsNone(self.client.request_json('fixture', 'first request', {'type': 'ARRAY'}))
                self.assertIsNone(self.client.request_json('fixture', 'second request', {'type': 'ARRAY'}))
        self.assertEqual(self.sdk.models.generate_content.call_count, 1)
        self.assertEqual(self.sdk.models.count_tokens.call_count, 1)
        self.assertFalse(self.client.retry_interpretation)
        sleep.assert_not_awaited()

    def test_backoff_delay_is_capped(self):
        self.client.initial_delay = 55
        self.sdk.models.generate_content.side_effect = [error(503), error(503), response([])]
        with patch('llm.asyncio.sleep', new_callable=AsyncMock) as sleep, patch('llm.random.uniform', return_value=10):
            with self.assertLogs('audit', 'WARNING'):
                self.assertEqual(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}), [])
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [60.0, 60.0])

    def test_retries_must_wait_for_the_same_five_rpm_pool(self):
        from quota import QuotaScheduler
        class Clock:
            now = 0.0
            def __call__(self): return self.now
            async def sleep(self, seconds): self.now += seconds
        clock = Clock(); self.client.rpm = 5
        self.sdk.models.generate_content.side_effect = [error(503)] * 4 + [response([])]
        def factory(rpm, tpm, concurrency):
            return QuotaScheduler(rpm, tpm, concurrency, clock=clock, sleep=clock.sleep)
        with patch('llm.QuotaScheduler', side_effect=factory), patch('llm.asyncio.sleep', new_callable=AsyncMock):
            with self.assertLogs('audit', 'WARNING'):
                self.assertEqual(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}), [])
        starts = [row['at'] for row in self.client.scheduler.history]
        self.assertEqual(len(starts), 6)
        self.assertGreaterEqual(starts[-1], 60)
        for instant in starts:
            self.assertLessEqual(sum(instant <= t < instant + 60 for t in starts), 5)

    def test_quota_diagnostics_exclude_sensitive_provider_fields(self):
        import json
        body = {'error': {'message': 'PRIVATE-FIXTURE', 'details': [
            {'violations': [{'quotaId': 'daily', 'quotaValue': '20', 'quotaDimensions': {'project': 'PRIVATE-FIXTURE'}}]},
            {'retryDelay': '3600s'}]}}
        self.sdk.models.generate_content.side_effect = error(429, body=body)
        with self.assertLogs('audit', 'WARNING') as captured:
            self.assertIsNone(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}))
        self.assertEqual(self.client.calls[-1]['quota_violations'], [{'quotaId': 'daily', 'quotaValue': '20'}])
        self.assertNotIn('PRIVATE-FIXTURE', json.dumps(self.client.calls) + str(captured.output))


if __name__ == '__main__': unittest.main()
