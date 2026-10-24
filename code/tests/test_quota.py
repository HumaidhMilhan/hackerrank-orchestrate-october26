"""Shared quota scheduling with a virtual clock; no live API or minute-long sleeps."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quota import QuotaScheduler, QuotaCapacityError


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now
    async def sleep(self, delay):
        self.now += delay
        await asyncio.sleep(0)


class QuotaTests(unittest.IsolatedAsyncioTestCase):
    async def test_sixth_request_waits_for_rolling_minute(self):
        clock = Clock(); scheduler = QuotaScheduler(5, 250000, 2, clock=clock, sleep=clock.sleep)
        self.addAsyncCleanup(scheduler.aclose)
        started = []
        async def operation(): started.append(clock()); return 'ok'
        await asyncio.gather(*(scheduler.call(operation, tokens=10) for _ in range(6)))
        self.assertEqual(len(started), 6)
        for instant in started:
            self.assertLessEqual(sum(instant <= t < instant + 60 for t in started), 5)
        self.assertGreaterEqual(max(started), 60)

    async def test_input_tokens_gate_even_when_rpm_available(self):
        clock = Clock(); scheduler = QuotaScheduler(100, 6, 1, clock=clock, sleep=clock.sleep)
        self.addAsyncCleanup(scheduler.aclose)
        started = []
        async def operation(): started.append(clock())
        for _ in range(3): await scheduler.call(operation, tokens=3)
        self.assertEqual(started, [0, 0, 60])

    async def test_concurrency_is_shared_and_cancelled_queued_work_never_runs(self):
        scheduler = QuotaScheduler(100, 10000, 2)
        self.addAsyncCleanup(scheduler.aclose)
        release, both_started = asyncio.Event(), asyncio.Event()
        active = peak = started = 0
        async def operation():
            nonlocal active, peak, started
            active += 1; started += 1; peak = max(peak, active)
            if active == 2: both_started.set()
            await release.wait()
            active -= 1
        tasks = [asyncio.create_task(scheduler.call(operation, tokens=1)) for _ in range(3)]
        await asyncio.wait_for(both_started.wait(), 1)
        tasks[-1].cancel(); release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(peak, 2)
        self.assertEqual(started, 2)

    async def test_failed_attempt_keeps_its_quota_reservation(self):
        clock = Clock(); scheduler = QuotaScheduler(100, 6, 1, clock=clock, sleep=clock.sleep)
        self.addAsyncCleanup(scheduler.aclose)
        async def fail(): raise TimeoutError()
        with self.assertRaises(TimeoutError): await scheduler.call(fail, tokens=6)
        async def succeed(): return clock()
        self.assertEqual(await scheduler.call(succeed, tokens=6), 60)

    async def test_oversized_request_is_rejected_without_network_work(self):
        scheduler = QuotaScheduler(5, 6, 2)
        self.addAsyncCleanup(scheduler.aclose)
        called = False
        async def operation():
            nonlocal called
            called = True
        with self.assertRaises(QuotaCapacityError): await scheduler.call(operation, tokens=7)
        self.assertFalse(called)

    async def test_guard_is_rechecked_after_waiting_for_quota(self):
        clock = Clock(); scheduler = QuotaScheduler(1, 10, 1, clock=clock, sleep=clock.sleep)
        self.addAsyncCleanup(scheduler.aclose)
        async def operation(): return 'ok'
        await scheduler.call(operation, tokens=1)
        def guard():
            if clock() >= 60: raise RuntimeError('provider cooldown')
        with self.assertRaisesRegex(RuntimeError, 'provider cooldown'):
            await scheduler.call(operation, tokens=1, guard=guard)
        self.assertEqual(len(scheduler.history), 1)


if __name__ == '__main__': unittest.main()
