"""Atomic artifacts survive temporary sharing failures without false success."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import atomic_json


class AtomicWriteTests(unittest.TestCase):
    def test_transient_replace_denial_preserves_old_file_until_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'state.json';target.write_text('{"old":true}')
            original=Path.replace;calls=[]
            def flaky(source,destination):
                calls.append(1)
                if len(calls)<=2:
                    self.assertEqual(json.loads(target.read_text()),{'old':True})
                    raise PermissionError('temporary sharing failure')
                return original(source,destination)
            with patch.object(Path,'replace',new=flaky),patch('time.sleep'):
                try:atomic_json(target,{'new':True})
                except PermissionError:self.fail('temporary sharing failure should be retried')
            self.assertEqual(json.loads(target.read_text()),{'new':True})
            self.assertEqual(len(calls),3)

    def test_permanent_denial_is_bounded_and_does_not_destroy_previous_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'state.json';target.write_text('{"old":true}')
            with patch.object(Path,'replace',side_effect=PermissionError('still denied')) as replace,patch('time.sleep'):
                with self.assertRaises(PermissionError):atomic_json(target,{'new':True})
            self.assertLessEqual(replace.call_count,5)
            self.assertEqual(json.loads(target.read_text()),{'old':True})

    def test_other_filesystem_errors_are_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path,'replace',side_effect=FileNotFoundError('missing')) as replace:
                with self.assertRaises(FileNotFoundError):atomic_json(Path(directory)/'state.json',{})
            self.assertEqual(replace.call_count,1)
