"""Fictional request tests for bounded, grounded intent review."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stage1 import interpret_requests


def item(cid='demo', intent='DELETION', confidence=0.99, phrase='Delete my account'):
    return dict(case_id=cid, intent=intent, confidence=confidence, supporting_phrase=phrase)


class Client:
    enabled = True
    intent_review_model = 'secondary'
    intent_confidence_threshold = 0.85
    intent_batch_size = 5
    retry_interpretation = False
    def __init__(self, replies): self.replies = iter(replies); self.requests = []
    def request_json(self, task, prompt, schema, validator=None):
        self.requests.append((task, prompt)); value = next(self.replies)
        if value is not None and validator:
            try: return validator(value)
            except (ValueError, TypeError, KeyError): return None
        return value


class IntentRoutingTests(unittest.TestCase):
    def run_case(self, replies, text='Delete my account'):
        client = Client(replies)
        return interpret_requests([dict(case_id='demo', request_text=text)], client)['demo'], client

    def test_high_confidence_consistent_primary_needs_no_review(self):
        result, client = self.run_case([[item()]])
        self.assertEqual(result['intent'], 'DELETION')
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(result['confidence'], 0.99)

    def test_low_confidence_is_reviewed_independently(self):
        result, client = self.run_case([[item(confidence=0.5)], [item(confidence=0.98)]])
        self.assertEqual([t for t,p in client.requests], ['intent', 'intent_review'])
        self.assertEqual(result['method'], 'model_review')
        self.assertNotIn('0.5', client.requests[1][1])

    def test_high_confidence_rule_conflict_still_escalates(self):
        result, client = self.run_case([[item(intent='NON_DELETION')], [item()]])
        self.assertEqual(result['intent'], 'DELETION')
        self.assertEqual(result['method'], 'model_review')

    def test_invalid_primary_is_protocol_failure_not_semantic_review(self):
        for invalid in [None, True, 'high', float('nan'), 1.1]:
            with self.subTest(invalid=invalid):
                result, client = self.run_case([[item(confidence=invalid)], [item()]])
                self.assertEqual(result['method'], 'rules')
                self.assertEqual(len(client.requests),1)

    def test_failed_or_uncertain_secondary_uses_locked_fallback(self):
        for secondary in [None, [item(confidence=0.1)], [item(phrase='invented')]]:
            with self.subTest(secondary=secondary):
                result, client = self.run_case([[item(confidence=0.2)], secondary])
                self.assertEqual(result['method'], 'rules')
                self.assertEqual(result['intent'], 'DELETION')
                self.assertTrue(result['warnings'])

    def test_secondary_only_receives_flagged_cases(self):
        client = Client([[item('a'), item('b', confidence=0.2)], [item('b')]])
        result = interpret_requests([{'case_id': cid, 'request_text': 'Delete my account'} for cid in ['a','b']], client)
        self.assertEqual(result['a']['method'], 'model')
        self.assertEqual(result['b']['method'], 'model_review')
        self.assertNotIn('"case_id": "a"', client.requests[1][1])
