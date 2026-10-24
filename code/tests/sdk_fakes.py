"""Small async SDK fixtures; never use actual API credentials in tests."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from google.genai import errors


def response(value):
    return SimpleNamespace(text=json.dumps(value), usage_metadata=SimpleNamespace(
        prompt_token_count=11, candidates_token_count=3, cached_content_token_count=0, thoughts_token_count=0))


def error(code, headers=None, body=None):
    import httpx
    raw = httpx.Response(code, headers=headers or {})
    return errors.APIError(code, body or {'error': {'message': 'fixture', 'code': code}}, response=raw)


class FakeSDK:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.models = SimpleNamespace(count_tokens=AsyncMock(return_value=SimpleNamespace(total_tokens=10)),
                                      generate_content=AsyncMock(return_value=response([])))
        self.aio = self
        self.aclose = AsyncMock()
    def close(self): pass
