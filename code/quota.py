"""One async queue owns every SDK request and its rolling-minute reservation."""
import asyncio
import logging
import time
import json
import inspect
import math
import re
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
                 concurrency_limiter=None, settle_daily=False, settle_minute=False):
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
        self.settle_minute = settle_minute
        self.in_flight = {}
        self.provider_remaining, self.provider_reset, self.provider_epoch = None, 0.0, 0
        self.provider_limit=self.tpm
        self.changed=asyncio.Event()
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.day_window = deque()
        self.ledger_invalid = False
        if self.ledger_path and self.ledger_path.is_file():
            try:
                saved=json.loads(self.ledger_path.read_text(encoding='utf-8'))
                items = saved['reservations']
                known_limit=saved.get('provider_limit',self.tpm)
                if type(known_limit) is not int or known_limit<=0:raise ValueError('invalid provider token limit')
                self.provider_limit=min(self.tpm,known_limit)
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
                provider = saved.get('provider')
                if provider is not None:
                    remaining, reset = provider['remaining'], provider['reset_wall']
                    if type(remaining) is not int or not math.isfinite(reset):
                        raise ValueError('invalid provider quota snapshot')
                    if reset > self.wall_clock():
                        self.provider_remaining = remaining
                        self.provider_reset = self.clock() + reset - self.wall_clock()
            except (ValueError, TypeError, KeyError, OSError):
                self.ledger_invalid = True

    def _persist(self):
        if self.ledger_path:
            try:
                state = {'reservations':[dict(item) for item in self.day_window],'provider_limit':self.provider_limit}
                if self.provider_remaining is not None:
                    state['provider'] = {'remaining':self.provider_remaining,
                        'reset_wall':self.wall_clock()+max(0,self.provider_reset-self.clock())}
                atomic_json(self.ledger_path,state)
            except OSError as exc:
                self.ledger_invalid = True
                raise DailyQuotaError('cannot persist local quota reservations') from exc

    async def call(self, operation, *, tokens=0, actual_tokens=None, guard=None, label='generate_content',rate_headers=None):
        if self.closed:
            raise RuntimeError('quota scheduler is closed')
        if type(tokens) is not int or tokens < 0 or tokens > min(self.tpm,self.provider_limit):
            raise QuotaCapacityError('request exceeds configured per-minute input-token capacity')
        if not self.workers:
            self.workers = [asyncio.create_task(self._worker()) for _ in range(self.max_concurrency)]
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((future, operation, tokens, actual_tokens, guard, label,rate_headers))
        return await future

    def _expire_provider(self):
        if self.provider_remaining is not None and self.clock() >= self.provider_reset:
            self.provider_remaining = None
            self.provider_epoch += 1

    async def _headers(self, headers, completed):
        """Header headroom is an upper bound, never permission to drop other work."""
        try:
            remaining=int(headers['x-ratelimit-remaining-tokens'])
            duration=headers['x-ratelimit-reset-tokens']
            parts=re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h|d)',duration)
            if parts and ''.join(n+u for n,u in parts)==duration:
                delay=sum(float(n)*{'ms':.001,'s':1,'m':60,'h':3600,'d':86400}[u] for n,u in parts)
            else:delay=float(duration)
            limit=int(headers.get('x-ratelimit-limit-tokens',self.tpm))
            if remaining < 0 or limit <= 0 or not math.isfinite(delay) or delay <= 0:return
        except (KeyError,TypeError,ValueError):return
        async with self.lock:
            self._expire_provider()
            self.provider_limit=min(self.provider_limit,limit,self.tpm)
            pending=[x for x in self.in_flight.values() if x is not completed]
            # Keep negative debt: clipping it to zero would let a later unused
            # reservation refund create tokens beyond the authoritative header.
            available=min(remaining,limit,self.tpm)-sum(x['tokens'] for x in pending)
            if self.provider_remaining is None:
                self.provider_remaining=available
                for item in pending:item['_provider_epoch']=self.provider_epoch
            else:self.provider_remaining=min(self.provider_remaining,available)
            self.provider_reset=max(self.provider_reset,self.clock()+delay)
            self._persist()
            self.changed.set()

    async def _admit(self, tokens, guard, label):
        while True:
            async with self.lock:
                if guard:
                    checked = guard()
                    if inspect.isawaitable(checked): await checked
                now = self.clock()
                self._expire_provider()
                if tokens>self.provider_limit:raise QuotaCapacityError('request exceeds provider token capacity')
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
                capacity=min(self.tpm,self.provider_limit)
                if used + tokens > capacity:
                    remaining = used
                    for item in self.window:
                        remaining -= item['tokens']
                        if remaining + tokens <= capacity:
                            delay = max(delay, item['at'] + 60 - now)
                            break
                if self.provider_remaining is not None and tokens > self.provider_remaining:
                    delay=max(delay,self.provider_reset-now)
                if delay <= 0:
                    entry = {'at': now, 'tokens': tokens, 'operation': label}
                    self.window.append(entry)
                    self.history.append(entry)
                    if self.provider_remaining is not None:
                        self.provider_remaining-=tokens
                        entry['_provider_epoch']=self.provider_epoch
                    if self.rpd or self.tpd or self.ledger_path:
                        entry['wall_at'] = self.wall_clock()
                        daily = {'wall_at':entry['wall_at'], 'tokens':tokens, 'minute_tokens':tokens, 'operation':label}
                        entry['_daily'] = daily
                        self.day_window.append(daily)
                        self._persist()
                    self.in_flight[id(entry)]=entry
                    return entry
                self.changed.clear()
            self.logger.info('QUOTA | waiting %.2fs | RPM %d/%d | reserved TPM %d/%d | queued=%d',
                             delay, len(self.window), self.rpm, used, min(self.tpm,self.provider_limit), self.queue.qsize())
            timer=asyncio.create_task(self.sleep(delay));changed=asyncio.create_task(self.changed.wait())
            try:await asyncio.wait([timer,changed],return_when=asyncio.FIRST_COMPLETED)
            finally:
                for pending in [timer,changed]:
                    if not pending.done():pending.cancel()
                await asyncio.gather(timer,changed,return_exceptions=True)

    async def _worker(self):
        while True:
            job = await self.queue.get()
            future, operation, tokens, actual_tokens, guard, label,rate_headers = job
            acquired = False
            entry = None
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
                    if type(actual) is not int or actual < 0:actual=None
                    previous=entry['tokens']
                    entry['tokens'] = int(actual) if self.settle_minute and actual is not None else max(previous,int(actual or 0))
                    self._expire_provider()
                    if self.provider_remaining is not None and entry.get('_provider_epoch')==self.provider_epoch:
                        self.provider_remaining=min(self.provider_limit,self.provider_remaining+previous-entry['tokens'])
                    if '_daily' in entry:
                        daily = entry['_daily']
                        daily['minute_tokens'] = entry['tokens']
                        daily['tokens'] = int(actual) if self.settle_daily and actual is not None else entry['tokens']
                    self._persist()
                    self.changed.set()
                if rate_headers:await self._headers(rate_headers(result),entry)
                if not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                if not future.done():
                    future.cancel()
                if self.closed:
                    raise
            except Exception as exc:
                if rate_headers and entry is not None:
                    try:await self._headers(rate_headers(None),entry)
                    except Exception as header_error:exc=header_error
                if not future.done():
                    future.set_exception(exc)
            finally:
                if entry is not None:self.in_flight.pop(id(entry),None)
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
