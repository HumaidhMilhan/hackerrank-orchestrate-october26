"""Transport retry behavior, using mocked HTTP instead of spending API quota."""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm import ModelClient


def response(value):
    return io.BytesIO(json.dumps({'candidates': [{'content': {'parts': [{'text': json.dumps(value)}]}}],
                                'usageMetadata': {'promptTokenCount': 11, 'candidatesTokenCount': 3}}).encode())


def error(code, headers=None, body=None):
    return urllib.error.HTTPError('https://fixture.invalid', code, 'fixture', headers or {},
                                  io.BytesIO(json.dumps(body or {}).encode()))


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict('os.environ', {'GEMINI_API_KEY': 'fixture-key', 'GEMINI_TEXT_MODEL': 'fixture-model'})
        env.start(); self.addCleanup(env.stop)
        self.client = ModelClient(Path(self.temp.name))

    def test_transient_errors_back_off_with_jitter_and_count_every_call(self):
        failures = [error(503), error(408), urllib.error.URLError('fixture'), TimeoutError()]
        with patch('urllib.request.urlopen', side_effect=failures + [response([])]) as network, \
             patch('llm.time.sleep') as sleep, patch('llm.random.uniform', return_value=0.2):
            with self.assertLogs('audit', 'WARNING'):
                self.assertEqual(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}), [])
        self.assertEqual(network.call_count, 5)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.2, 2.2, 4.2, 8.2])
        self.assertEqual(len(self.client.calls), 5)
        self.assertEqual(sum(call['success'] for call in self.client.calls), 1)
        self.assertEqual(self.client.calls[-1]['input_tokens'], 11)

    def test_transport_exhaustion_does_not_get_an_extra_stage1_retry(self):
        from stage1 import interpret_requests
        with patch('urllib.request.urlopen', side_effect=lambda *a, **kw: (_ for _ in ()).throw(error(503))) as network, \
             patch('llm.time.sleep'):
            with self.assertLogs('audit', 'WARNING'):
                result = interpret_requests([{'case_id': 'demo', 'request_text': 'Delete my account.'}], self.client)
        self.assertEqual(network.call_count, 5)
        self.assertEqual(len(self.client.calls), 5)
        self.assertEqual(result['demo']['method'], 'rules')

    def test_permanent_errors_are_not_retried_by_transport_or_stages(self):
        from stage1 import interpret_requests
        from stage2 import interpret_media
        for code in [400, 402, 403, 404]:
            with self.subTest(code=code), patch('urllib.request.urlopen', side_effect=error(code)) as network, \
                 patch('llm.time.sleep') as sleep:
                with self.assertLogs('audit', 'WARNING'):
                    result = interpret_requests([{'case_id': 'demo', 'request_text': 'Delete my account.'}], self.client)
                self.assertEqual(result['demo']['method'], 'rules')
                self.assertEqual(network.call_count, 1)
                sleep.assert_not_called()
        with patch('urllib.request.urlopen', side_effect=error(403)) as network:
            with self.assertLogs('audit', 'WARNING'):
                self.assertIsNone(interpret_media({'file_id': 'fixture', 'captured_at': '2026-01-01T00:00:00Z'},
                                                self.client, b'fixture-image', 'fixture'))
            self.assertEqual(network.call_count, 1)

    def test_invalid_interpretation_uses_one_repair_without_transport_sleep(self):
        from stage1 import interpret_requests
        def intent(phrase):
            return response([{'case_id': 'demo', 'intent': 'DELETION', 'supporting_phrase': phrase}])
        with patch('urllib.request.urlopen', side_effect=[intent('invented'), intent('Delete my account')]) as network, \
             patch('llm.time.sleep') as sleep:
            with self.assertLogs('audit', 'WARNING'):
                result = interpret_requests([{'case_id': 'demo', 'request_text': 'Delete my account.'}], self.client)
        self.assertEqual(network.call_count, 2)
        self.assertEqual(result['demo']['method'], 'model')
        sleep.assert_not_called()

    def test_retry_after_header_is_respected(self):
        with patch('urllib.request.urlopen', side_effect=[error(429, {'Retry-After': '3'}), response([])]), \
             patch('llm.time.sleep') as sleep, patch('llm.random.uniform', return_value=0):
            with self.assertLogs('audit', 'WARNING'):
                self.assertEqual(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}), [])
        sleep.assert_called_once_with(3.0)

    def test_long_google_retry_delay_defers_same_model_without_sleeping_hours(self):
        body = {'error': {'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '3600s'}]}}
        with patch('urllib.request.urlopen', side_effect=error(429, body=body)) as network, patch('llm.time.sleep') as sleep:
            with self.assertLogs('audit', 'WARNING'):
                self.assertIsNone(self.client.request_json('fixture', 'first request', {'type': 'ARRAY'}))
                self.assertIsNone(self.client.request_json('fixture', 'second request', {'type': 'ARRAY'}))
        self.assertEqual(network.call_count, 1)
        self.assertEqual(len(self.client.calls), 1)
        self.assertFalse(self.client.retry_interpretation)
        sleep.assert_not_called()

    def test_backoff_delay_is_capped(self):
        self.client.initial_delay = 55
        with patch('urllib.request.urlopen', side_effect=[error(503), error(503), response([])]), \
             patch('llm.time.sleep') as sleep, patch('llm.random.uniform', return_value=10):
            with self.assertLogs('audit', 'WARNING'):
                self.assertEqual(self.client.request_json('fixture', 'fixture', {'type': 'ARRAY'}), [])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [60.0, 60.0])


if __name__ == '__main__':
    unittest.main()
