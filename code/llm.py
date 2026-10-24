"""Gemini REST boundary: interpretation only, bounded callers, sanitized errors."""
import base64
import http.client
import json
import logging
import math
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from email.utils import parsedate_to_datetime

from common import atomic_json, digest


def retry_after_seconds(error):
    """Read only retry timing; never log provider bodies or credential-bearing URLs."""
    delays = []
    header = (error.headers or {}).get('Retry-After')
    if header:
        try:
            delays.append(float(header))
        except (ValueError, TypeError):
            try:
                delays.append(parsedate_to_datetime(header).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
    try:
        body = json.loads(error.read(65536))
        for detail in body.get('error', {}).get('details', []):
            delay = detail.get('retryDelay')
            if isinstance(delay, str) and delay.endswith('s'):
                delays.append(float(delay[:-1]))
    except (ValueError, TypeError, AttributeError, OSError):
        pass
    finally:
        error.close()
    return max((delay for delay in delays if math.isfinite(delay) and delay >= 0), default=0.0)


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
        self.max_retries = 4
        self.initial_delay = 1.0
        self.max_delay = 60.0
        self.retry_interpretation = False
        self.cooldown_until = {}
        self.logger = logging.getLogger('audit')

    @property
    def enabled(self):
        return bool(self.key and self.text_model)

    def configuration(self):
        return {'provider': 'gemini' if self.enabled else 'offline', 'text_model': self.text_model,
                'vision_model': self.vision_model, 'key_available': bool(self.key)}

    def request_json(self, task, prompt, schema, image=None, mime='image/png', validator=None):
        """Bound transport retries here; callers may repair one invalid interpretation."""
        self.retry_interpretation = False
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
                self.retry_interpretation = True
                return result
            except (ValueError, TypeError, KeyError):
                pass
        if self.cooldown_until.get(model, 0) > time.monotonic():
            self.logger.warning('%s: provider retry window still active; using available evidence/fallback', task)
            return None
        parts = [{'text': prompt}]
        if image:
            parts.append({'inlineData': {'mimeType': mime, 'data': base64.b64encode(image).decode('ascii')}})
        payload = {'contents': [{'role': 'user', 'parts': parts}],
                   'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json',
                                        'responseSchema': schema, 'maxOutputTokens': 16384}}
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + urllib.parse.quote(model.removeprefix('models/'), safe='') + ':generateContent'
        request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                         headers={'Content-Type': 'application/json', 'x-goog-api-key': self.key})
        for attempt in range(self.max_retries + 1):
            usage = {'provider': 'gemini', 'model': model, 'task': task, 'success': False,
                     'attempt': attempt + 1, 'input_tokens': None, 'output_tokens': None,
                     'cached_tokens': None, 'thinking_tokens': None}
            started = time.monotonic()
            transient, retry_after = False, 0.0
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
                self.retry_interpretation = True
                atomic_json(cache, result)
                return result
            except urllib.error.HTTPError as exc:
                usage.update(error_type=type(exc).__name__, http_status=exc.code)
                transient = exc.code in {408, 429} or 500 <= exc.code <= 599
                if transient:
                    retry_after = retry_after_seconds(exc)
                else:
                    exc.close()
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
                usage['error_type'] = type(exc).__name__
                transient = True
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                usage['error_type'] = type(exc).__name__
                self.retry_interpretation = True
            finally:
                usage['seconds'] = round(time.monotonic() - started, 3)
                self.calls.append(usage)
            reason = usage['error_type'] + (f", HTTP {usage['http_status']}" if 'http_status' in usage else '')
            if retry_after > self.max_delay:
                self.cooldown_until[model] = time.monotonic() + retry_after
                usage['provider_retry_after_seconds'] = retry_after
                self.logger.warning('%s request failed (%s); provider asks %.1fs wait; deferring model calls and continuing with fallback',
                                    task, reason, retry_after)
                return None
            if not transient or attempt == self.max_retries:
                self.logger.warning('%s request failed (%s); %s; continuing with fallback/interpretation repair',
                                    task, reason, 'retry budget exhausted' if transient else 'no transport retry')
                return None
            base = min(self.max_delay, self.initial_delay * (2 ** attempt))
            delay = max(retry_after, min(self.max_delay, base + random.uniform(0, base * 0.25)))
            usage['backoff_seconds'] = delay
            self.logger.warning('%s request failed (%s); retry %d/%d in %.2fs',
                                task, reason, attempt + 1, self.max_retries, delay)
            time.sleep(delay)
