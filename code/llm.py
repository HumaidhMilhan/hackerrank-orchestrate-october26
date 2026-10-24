"""Google async SDK behind one quota queue; deterministic audit code stays synchronous."""
import atexit
import asyncio
import contextvars
import json
import logging
import math
import os
import random
import threading
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
from google import genai
from google.genai import errors, types

from common import atomic_json, digest
from quota import QuotaScheduler, QuotaCapacityError


class DeferredCall(Exception):
    pass


def retry_after_seconds(error):
    """Read retry timing; never log SDK exception text, bodies, or URLs."""
    delays = []
    response = getattr(error, 'response', None)
    header = response.headers.get('Retry-After') if response is not None else None
    if header:
        try:
            delays.append(float(header))
        except (ValueError, TypeError):
            try:
                delays.append(parsedate_to_datetime(header).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
    body = getattr(error, 'details', {})
    if isinstance(body, dict):
        error_body = body.get('error', body)
        details = error_body.get('details', []) if isinstance(error_body, dict) else []
        for detail in details if isinstance(details, list) else []:
            delay = detail.get('retryDelay') if isinstance(detail, dict) else None
            if isinstance(delay, str) and delay.endswith('s'):
                try:
                    delays.append(float(delay[:-1]))
                except ValueError:
                    pass
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
        self.key = '' if offline else (os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY', ''))
        self.text_model = os.getenv('GEMINI_TEXT_MODEL') or os.getenv('GEMINI_MODEL') or 'gemini-3.6-flash'
        self.vision_model = os.getenv('GEMINI_VISION_MODEL') or self.text_model
        self.rpm = int(os.getenv('GEMINI_RPM', '5'))
        self.tpm = int(os.getenv('GEMINI_TPM', '250000'))
        self.max_concurrency = int(os.getenv('GEMINI_MAX_CONCURRENCY', '2'))
        if min(self.rpm, self.tpm, self.max_concurrency) <= 0:
            raise ValueError('quota limits must be positive')
        self.timeout = float(os.getenv('AUDIT_API_TIMEOUT', '45'))
        self.max_retries, self.initial_delay, self.max_delay = 4, 1.0, 60.0
        self.cache_dir = Path(cache_dir)
        self.calls, self.cache_hits = [], 0
        self.cooldown_until = {}
        self._repair = contextvars.ContextVar('repair-' + str(id(self)), default=False)
        self._loop = self._thread = self._sdk = self.scheduler = None
        self._httpx_client = None
        self._pending_requests = set()
        self._start_lock = threading.Lock()
        self._closed = False
        self.logger = logging.getLogger('audit')
        atexit.register(self.close)

    @property
    def enabled(self):
        return bool(self.key and self.text_model)

    @property
    def retry_interpretation(self):
        return self._repair.get()

    def configuration(self):
        return {'provider': 'gemini' if self.enabled else 'offline', 'text_model': self.text_model,
                'vision_model': self.vision_model, 'key_available': bool(self.key),
                'transport': 'google-genai-async', 'rpm': self.rpm, 'tpm': self.tpm,
                'max_concurrency': self.max_concurrency}

    def _ensure_loop(self):
        with self._start_lock:
            if self._closed:
                raise RuntimeError('model client is closed')
            if self._loop is None:
                ready = threading.Event()
                def run_loop():
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                    ready.set()
                    self._loop.run_forever()
                    self._loop.close()
                self._thread = threading.Thread(target=run_loop, name='gemini-quota', daemon=True)
                self._thread.start()
                ready.wait()

    def request_json(self, *args, **kwargs):
        """Sync stages enqueue work; they never call the SDK themselves."""
        if not self.enabled:
            self._repair.set(False)
            return None
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(self._dispatch(*args, **kwargs), self._loop)
        try:
            value, repair = future.result()
        except BaseException:
            future.cancel()
            raise
        self._repair.set(repair)
        return value

    async def request_json_async(self, *args, **kwargs):
        """Concurrent tasks also enqueue on the same loop and shared quota pool."""
        if not self.enabled:
            self._repair.set(False)
            return None
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(self._dispatch(*args, **kwargs), self._loop)
        value, repair = await asyncio.wrap_future(future)
        self._repair.set(repair)
        return value

    async def _dispatch(self, *args, **kwargs):
        if self._closed:
            raise asyncio.CancelledError()
        task = asyncio.current_task()
        self._pending_requests.add(task)
        try:
            return await self._request(*args, **kwargs)
        finally:
            self._pending_requests.discard(task)

    def _guard(self, model):
        if self.cooldown_until.get(model, 0) > time.monotonic():
            raise DeferredCall('provider cooldown')

    def _initialize_sdk(self):
        if self._sdk is None:
            # The SDK's auto-selected aiohttp path has its own reconnect retry.
            # An explicit httpx transport keeps each SDK attempt inside our quota.
            self._httpx_client = httpx.AsyncClient(timeout=self.timeout,
                transport=httpx.AsyncHTTPTransport(retries=0))
            self._sdk = genai.Client(api_key=self.key, http_options=types.HttpOptions(
                timeout=int(self.timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1),
                httpx_async_client=self._httpx_client))
            self.scheduler = QuotaScheduler(self.rpm, self.tpm, self.max_concurrency)

    async def _physical(self, task, model, operation, contents, tokens, attempt, usage, config=None):
        """Only SDK invocation point, always executed by a quota worker."""
        usage.update({'provider': 'gemini', 'model': model, 'task': task, 'operation': operation,
                 'success': False, 'attempt': attempt, 'reserved_input_tokens': tokens,
                 'input_tokens': None, 'output_tokens': None, 'cached_tokens': None, 'thinking_tokens': None})
        started = time.monotonic()
        try:
            if operation == 'count_tokens':
                result = await self._sdk.aio.models.count_tokens(model=model, contents=contents)
                usage.update(input_tokens=0, output_tokens=0, cached_tokens=0, thinking_tokens=0,
                             counted_input_tokens=result.total_tokens, success=True)
            else:
                result = await self._sdk.aio.models.generate_content(model=model, contents=contents, config=config)
                metadata = result.usage_metadata
                if metadata:
                    usage.update(input_tokens=metadata.prompt_token_count, output_tokens=metadata.candidates_token_count,
                                 cached_tokens=metadata.cached_content_token_count or 0, thinking_tokens=metadata.thoughts_token_count or 0)
            return result
        except BaseException as exc:
            usage['error_type'] = type(exc).__name__
            if isinstance(exc, errors.APIError):
                usage['http_status'] = exc.code
                body = exc.details if isinstance(exc.details, dict) else {}
                error_body = body.get('error', body)
                detail_items = error_body.get('details', []) if isinstance(error_body, dict) else []
                violations = []
                for detail in detail_items if isinstance(detail_items, list) else []:
                    for violation in detail.get('violations', []) if isinstance(detail, dict) else []:
                        if isinstance(violation, dict):
                            violations.append({key: violation[key] for key in ['quotaMetric', 'quotaId', 'quotaValue'] if key in violation})
                if violations:
                    usage['quota_violations'] = violations
            raise
        finally:
            usage['seconds'] = round(time.monotonic() - started, 3)
            self.calls.append(usage)

    async def _rpc(self, task, model, operation, contents, tokens=0, config=None):
        for attempt in range(self.max_retries + 1):
            usage = {}
            try:
                result = await self.scheduler.call(
                    lambda: self._physical(task, model, operation, contents, tokens, attempt + 1, usage, config),
                    tokens=tokens, guard=lambda: self._guard(model), label=operation,
                    actual_tokens=(lambda result: result.usage_metadata.prompt_token_count if result.usage_metadata else 0)
                    if operation == 'generate_content' else None)
                return result, usage
            except errors.APIError as exc:
                transient = exc.code in {408, 429} or 500 <= exc.code <= 599
                retry_after = retry_after_seconds(exc) if transient else 0.0
                reason = f'{type(exc).__name__}, HTTP {exc.code}'
            except (httpx.TransportError, TimeoutError, ConnectionError) as exc:
                transient, retry_after, reason = True, 0.0, type(exc).__name__
            if retry_after > self.max_delay:
                self.cooldown_until[model] = time.monotonic() + retry_after
                usage['provider_retry_after_seconds'] = retry_after
                self.logger.warning('%s %s failed (%s); provider asks %.1fs wait; deferring model calls', task, operation, reason, retry_after)
                return None
            if not transient or attempt == self.max_retries:
                self.logger.warning('%s %s failed (%s); %s; using fallback', task, operation, reason,
                                    'retry budget exhausted' if transient else 'no transport retry')
                return None
            base = min(self.max_delay, self.initial_delay * 2 ** attempt)
            delay = max(retry_after, min(self.max_delay, base + random.uniform(0, base * 0.25)))
            usage['backoff_seconds'] = delay
            self.logger.warning('%s %s failed (%s); retry %d/%d in %.2fs through quota queue',
                                task, operation, reason, attempt + 1, self.max_retries, delay)
            await asyncio.sleep(delay)

    async def _request(self, task, prompt, schema, image=None, mime='image/png', validator=None):
        model = self.vision_model if image else self.text_model
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
                return result, True
            except (ValueError, TypeError, KeyError):
                pass
        try:
            self._guard(model)
            self._initialize_sdk()
            contents = [types.Content(role='user', parts=[types.Part.from_text(text=prompt)] +
                        ([types.Part.from_bytes(data=image, mime_type=mime)] if image else []))]
            count_path = self.cache_dir / 'token_counts' / (digest({'prompt': prompt, 'image': digest(image) if image else None, 'model': model}) + '.json')
            if count_path.is_file():
                count = json.loads(count_path.read_text(encoding='utf-8'))['input_tokens']
            else:
                counted = await self._rpc(task, model, 'count_tokens', contents)
                if counted is None:
                    return None, False
                count = counted[0].total_tokens
                if type(count) is not int or count < 0:
                    raise ValueError('invalid provider token count')
                atomic_json(count_path, {'input_tokens': count})
            # Count all contents, then conservatively reserve schema/config overhead.
            reserved = count + len(json.dumps(schema, ensure_ascii=False).encode('utf-8')) + 256
            config = types.GenerateContentConfig(response_mime_type='application/json', response_schema=schema,
                                                 max_output_tokens=16384,
                                                 automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
            result = await self._rpc(task, model, 'generate_content', contents, reserved, config)
            if result is None:
                return None, False
            result, generation_usage = result
            value = json.loads(result.text)
            if validator:
                accepted = validator(value)
                if accepted is not None:
                    value = accepted
            atomic_json(cache, value)
            generation_usage['success'] = True
            return value, True
        except DeferredCall:
            self.logger.warning('%s: provider retry window active; using available evidence/fallback', task)
            return None, False
        except QuotaCapacityError:
            self.logger.warning('%s: input exceeds configured TPM capacity; using fallback', task)
            return None, False
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            self.logger.warning('%s: invalid model response/config (%s); one interpretation repair may apply', task, type(exc).__name__)
            return None, True

    async def _shutdown(self):
        pending = list(self._pending_requests)
        for task in pending:
            task.cancel()
        if self.scheduler:
            await self.scheduler.aclose()
        await asyncio.gather(*pending, return_exceptions=True)
        if self._sdk:
            await self._sdk.aio.aclose()
            self._sdk.close()
        if self._httpx_client and not self._httpx_client.is_closed:
            await self._httpx_client.aclose()

    def close(self):
        with self._start_lock:
            if self._closed:
                return
            self._closed = True
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result()
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
        atexit.unregister(self.close)

    async def aclose(self):
        await asyncio.to_thread(self.close)
