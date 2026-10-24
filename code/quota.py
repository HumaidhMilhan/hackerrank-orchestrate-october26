"""One async queue owns every SDK request and its rolling-minute reservation."""
import asyncio
import logging
import time
from collections import deque


class QuotaCapacityError(ValueError):
    pass


class QuotaScheduler:
    def __init__(self, rpm=5, tpm=250000, max_concurrency=2, *, clock=time.monotonic, sleep=asyncio.sleep):
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
                    guard()
                now = self.clock()
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
                    return entry
            self.logger.info('QUOTA | waiting %.2fs | RPM %d/%d | input TPM %d/%d | queued=%d',
                             delay, len(self.window), self.rpm, used, self.tpm, self.queue.qsize())
            await self.sleep(delay)

    async def _worker(self):
        while True:
            job = await self.queue.get()
            future, operation, tokens, actual_tokens, guard, label = job
            try:
                if future.cancelled():
                    continue
                def checked_guard():
                    if future.cancelled():
                        raise asyncio.CancelledError()
                    if guard:
                        guard()
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
                    entry['tokens'] = max(entry['tokens'], int(actual_tokens(result) or 0))
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
