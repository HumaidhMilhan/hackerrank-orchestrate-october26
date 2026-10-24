"""Gemini REST boundary: interpretation only, bounded callers, sanitized errors."""
import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import atomic_json, digest


def load_env(path):
    if not Path(path).is_file():
        return
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        name = name.strip().removeprefix('export ')
        if name.isidentifier():
            os.environ.setdefault(name, value.strip().strip('\"\''))


class ModelClient:
    def __init__(self, cache_dir, offline=False):
        self.key = '' if offline else os.getenv('GEMINI_API_KEY', os.getenv('GOOGLE_API_KEY', ''))
        self.text_model = os.getenv('GEMINI_TEXT_MODEL', os.getenv('GEMINI_MODEL', ''))
        self.vision_model = os.getenv('GEMINI_VISION_MODEL', self.text_model)
        self.cache_dir = Path(cache_dir)
        self.calls = []
        self.cache_hits = 0
        self.timeout = float(os.getenv('AUDIT_API_TIMEOUT', '45'))
        self.logger = logging.getLogger('audit')

    @property
    def enabled(self):
        return bool(self.key and self.text_model)

    def configuration(self):
        return {'provider': 'gemini' if self.enabled else 'offline', 'text_model': self.text_model,
                'vision_model': self.vision_model, 'key_available': bool(self.key)}

    def request_json(self, task, prompt, schema, image=None, mime='image/png', validator=None):
        """One physical request; the caller owns its maximum two attempts."""
        model = self.vision_model if image else self.text_model
        if not self.key or not model:
            return None
        fingerprint = digest({'task': task, 'prompt': prompt, 'schema': schema,
                              'model': model, 'image': digest(image) if image else None, 'version': 1})
        cache = self.cache_dir / (fingerprint + '.json')
        if cache.is_file():
            try:
                result = json.loads(cache.read_text(encoding='utf-8'))
                if validator:
                    accepted = validator(result)
                    if accepted is not None:
                        result = accepted
                self.cache_hits += 1
                return result
            except (ValueError, TypeError, KeyError):
                pass
        parts = [{'text': prompt}]
        if image:
            parts.append({'inlineData': {'mimeType': mime, 'data': base64.b64encode(image).decode('ascii')}})
        payload = {'contents': [{'role': 'user', 'parts': parts}],
                   'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json',
                                        'responseSchema': schema, 'maxOutputTokens': 16384}}
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + urllib.parse.quote(model.removeprefix('models/'), safe='') + ':generateContent'
        request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                         headers={'Content-Type': 'application/json', 'x-goog-api-key': self.key})
        usage = {'provider': 'gemini', 'model': model, 'task': task, 'success': False,
                 'input_tokens': None, 'output_tokens': None, 'cached_tokens': None, 'thinking_tokens': None}
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
            metadata = body.get('usageMetadata', {})
            usage.update(input_tokens=metadata.get('promptTokenCount'), output_tokens=metadata.get('candidatesTokenCount'),
                         cached_tokens=metadata.get('cachedContentTokenCount', 0), thinking_tokens=metadata.get('thoughtsTokenCount', 0))
            text = ''.join(p.get('text', '') for p in body['candidates'][0]['content']['parts'] if not p.get('thought'))
            result = json.loads(text)
            if validator:
                accepted = validator(result)
                if accepted is not None:
                    result = accepted
            usage['success'] = True
            atomic_json(cache, result)
            return result
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
            # Provider exception bodies/URLs can contain credentials or request text.
            usage['error_type'] = type(exc).__name__
            if isinstance(exc, urllib.error.HTTPError):
                usage['http_status'] = exc.code
            self.logger.warning('%s model request failed (%s%s); bounded retry/fallback applies',
                                task, type(exc).__name__, f', HTTP {exc.code}' if isinstance(exc, urllib.error.HTTPError) else '')
            return None
        finally:
            usage['seconds'] = round(time.monotonic() - started, 3)
            self.calls.append(usage)
