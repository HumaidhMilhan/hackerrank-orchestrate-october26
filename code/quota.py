"""One async queue owns every SDK request and its rolling-minute reservation."""
import asyncio
import logging
import time
import json
import inspect
import math
from collections import deque
from pathlib import Path
from common import atomic_json


class QuotaCapacityError(ValueError):
    pass


class DailyQuotaError(QuotaCapacityError):
    pass


class QuotaScheduler:
    def __init__(self, rpm=5, tpm=250000, max_concurrency=2, *, clock=time.monotonic, sleep=asyncio.sleep,
                 rpd=None, tpd=None, ledger_path=None, wall_clock=time.time,
                 concurrency_limiter=None, settle_daily=False):
        if any(type(value) is not int or value <= 0 for value in [rpm, tpm, max_concurrency]):
            raise ValueError('quota limits must be positive integers')
        self.rpm, self.tpm, self.max_concurrency = rpm, tpm, max_concurrency
        self.clock, self.sleep = clock, sleep
        self.queue = asyncio.Queue()
        self.lock = asyncio.Lock()
        self.window = deque()
        self.history = []
        self.workers = []
        self.closed = False
        self.active = self.peak_concurrency = 0
        self.logger = logging.getLogger('audit')
        if any(value is not None and (type(value) is not int or value <= 0) for value in [rpd, tpd]):
            raise ValueError('daily quota limits must be positive integers')
        self.rpd, self.tpd, self.wall_clock = rpd, tpd, wall_clock
        self.concurrency_limiter, self.settle_daily = concurrency_limiter, settle_daily
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.day_window = deque()
        self.ledger_invalid = False
        if self.ledger_path and self.ledger_path.is_file():
            try:
                items = json.loads(self.ledger_path.read_text(encoding='utf-8'))['reservations']
                if not isinstance(items, list):
                    raise ValueError('invalid quota ledger list')
                for item in items:
                    if not isinstance(item, dict) or type(item.get('tokens')) is not int or item['tokens'] < 0:
                        raise ValueError('invalid quota ledger')
                    if (type(item.get('wall_at')) not in {int,float} or not math.isfinite(item['wall_at'])
                        or type(item.get('minute_tokens',item['tokens'])) is not int
                        or item.get('minute_tokens',item['tokens']) < 0):
                        raise ValueError('invalid quota ledger time/tokens')
                    age = self.wall_clock() - float(item['wall_at'])
                    if age < 0:
                        raise ValueError('quota clock moved backwards')
                    if age < 86400:
                        entry = {'at': self.clock() - age, 'tokens': item.get('minute_tokens', item['tokens']),
                                 'wall_at': item['wall_at'], 'operation': item.get('operation', 'restored')}
                        self.day_window.append(item)
                        if age < 60:
                            self.window.append(entry)
            except (ValueError, TypeError, KeyError, OSError):
                self.ledger_invalid = True

    def _persist(self):
        if self.ledger_path:
            try:
                atomic_json(self.ledger_path, {'reservations': [
                    dict(item) for item in self.day_window]})
            except OSError as exc:
                self.ledger_invalid = True
                raise DailyQuotaError('cannot persist local quota reservations') from exc

    async def call(self, operation, *, tokens=0, actual_tokens=None, guard=None, label='generate_content'):
        if self.closed:
            raise RuntimeError('quota scheduler is closed')
        if type(tokens) is not int or tokens < 0 or tokens > self.tpm:
            raise QuotaCapacityError('request exceeds configured per-minute input-token capacity')
        if not self.workers:
            self.workers = [asyncio.create_task(self._worker()) for _ in range(self.max_concurrency)]
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((future, operation, tokens, actual_tokens, guard, label))
        return await future

    async def _admit(self, tokens, guard, label):
        while True:
            async with self.lock:
                if guard:
                    checked = guard()
                    if inspect.isawaitable(checked): await checked
                now = self.clock()
                if self.ledger_invalid:
                    raise DailyQuotaError('local quota ledger unreadable; refusing untracked requests')
                while self.day_window and self.wall_clock() - self.day_window[0]['wall_at'] >= 86400:
                    self.day_window.popleft()
                if ((self.rpd and len(self.day_window) >= self.rpd) or
                    (self.tpd and sum(item['tokens'] for item in self.day_window) + tokens > self.tpd)):
                    raise DailyQuotaError('local rolling daily quota exhausted')
                while self.window and now - self.window[0]['at'] >= 60:
                    self.window.popleft()
                used = sum(item['tokens'] for item in self.window)
                delay = 0.0
                if len(self.window) >= self.rpm:
                    delay = self.window[-self.rpm]['at'] + 60 - now
                if used + tokens > self.tpm:
                    remaining = used
                    for item in self.window:
                        remaining -= item['tokens']
                        if remaining + tokens <= self.tpm:
                            delay = max(delay, item['at'] + 60 - now)
                            break
                if delay <= 0:
                    entry = {'at': now, 'tokens': tokens, 'operation': label}
                    self.window.append(entry)
                    self.history.append(entry)
                    if self.rpd or self.tpd or self.ledger_path:
                        entry['wall_at'] = self.wall_clock()
                        daily = {'wall_at':entry['wall_at'], 'tokens':tokens, 'minute_tokens':tokens, 'operation':label}
                        entry['_daily'] = daily
                        self.day_window.append(daily)
                        self._persist()
                    return entry
            self.logger.info('QUOTA | waiting %.2fs | RPM %d/%d | reserved TPM %d/%d | queued=%d',
                             delay, len(self.window), self.rpm, used, self.tpm, self.queue.qsize())
            await self.sleep(delay)

    async def _worker(self):
        while True:
            job = await self.queue.get()
            future, operation, tokens, actual_tokens, guard, label = job
            acquired = False
            try:
                if future.cancelled():
                    continue
                if self.concurrency_limiter:
                    await self.concurrency_limiter.acquire()
                    acquired = True
                async def checked_guard():
                    if future.cancelled():
                        raise asyncio.CancelledError()
                    if guard:
                        checked = guard()
                        if inspect.isawaitable(checked): await checked
                    if future.cancelled():
                        raise asyncio.CancelledError()
                entry = await self._admit(tokens, checked_guard, label)
                self.active += 1
                self.peak_concurrency = max(self.peak_concurrency, self.active)
                try:
                    result = await operation()
                finally:
                    self.active -= 1
                if actual_tokens:
                    # Do not refund unknown/overestimated attempts; raise reservations
                    # when returned usage exceeds the conservative preflight count.
                    actual = actual_tokens(result)
                    entry['tokens'] = max(entry['tokens'], int(actual or 0))
                    if '_daily' in entry:
                        daily = entry['_daily']
                        daily['minute_tokens'] = entry['tokens']
                        daily['tokens'] = int(actual) if self.settle_daily and actual is not None else entry['tokens']
                    self._persist()
                if not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                if not future.done():
                    future.cancel()
                if self.closed:
                    raise
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            finally:
                if acquired:
                    self.concurrency_limiter.release()
                self.queue.task_done()

    async def aclose(self):
        self.closed = True
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        while not self.queue.empty():
            future, *_ = self.queue.get_nowait()
            if not future.done():
                future.cancel()
            self.queue.task_done()
