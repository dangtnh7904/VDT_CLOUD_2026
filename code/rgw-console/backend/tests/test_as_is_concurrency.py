from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.modules.as_is import service as module
from app.modules.as_is.service import AsIsError
from app.services.executor_client import ExecutorClientError
import test_as_is as fixtures


class SignalledSemaphore:
    """Real waiting semaphore with an event for deterministic thread ordering."""

    def __init__(self):
        self.semaphore = threading.BoundedSemaphore(2)
        self.admitted = threading.Event()

    def acquire(self, **kwargs):
        acquired = self.semaphore.acquire(**kwargs)
        if acquired:
            self.admitted.set()
        return acquired

    def release(self):
        self.semaphore.release()


class AsIsConcurrencyTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AsIsTests()
        fixture.setUp()
        self.service, self.client = fixture.service, fixture.client
        self.slots = threading.BoundedSemaphore(2)
        self.waiters = SignalledSemaphore()
        for name, value in (
            ('SLOTS', self.slots), ('WAITING_SLOTS', self.waiters),
            ('COLLECTION_WAIT_SECONDS', 0.1),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_slots_reusable(self):
        for semaphore in (self.slots, self.waiters.semaphore):
            self.assertTrue(semaphore.acquire(blocking=False))
            self.assertTrue(semaphore.acquire(blocking=False))
            self.assertFalse(semaphore.acquire(blocking=False))
            semaphore.release()
            semaphore.release()

    def test_third_read_waits_then_reads_new_sources_without_exceeding_two_active(self):
        entered = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        active, maximum, calls = 0, 0, 0
        original = self.service._observe

        def read(*args):
            nonlocal active, maximum, calls
            with lock:
                active += 1
                maximum = max(maximum, active)
                calls += 1
                current = calls
                if calls == 2:
                    entered.set()
            try:
                if current <= 2:
                    if not release.wait(2):
                        raise RuntimeError('test reader did not release')
                    return {'read': current}
                return original(*args)
            finally:
                with lock:
                    active -= 1

        with patch.object(module, 'COLLECTION_WAIT_SECONDS', 2), \
             patch.object(self.service, '_observe', side_effect=read), \
             ThreadPoolExecutor(max_workers=3) as workers:
            first = workers.submit(self.service.observe, daemon_keys=['osd.0'])
            second = workers.submit(self.service.observe, daemon_keys=['osd.0'])
            try:
                self.assertTrue(entered.wait(1))
                third = workers.submit(self.service.observe, daemon_keys=['osd.0'])
                self.assertTrue(self.waiters.admitted.wait(1))
                self.assertFalse(third.done())
                self.assertEqual(calls, 2)
                self.client.version = 9
            finally:
                release.set()
            first.result(timeout=2)
            second.result(timeout=2)
            result = third.result(timeout=2)
        self.assertEqual(maximum, 2)
        self.assertEqual(result['daemons'][0]['fields']['used_kb'], 9)
        self.assertTrue(self.client.calls)
        self.assertEqual(self.service.repository.rows, {})
        self.assert_slots_reusable()

    def test_full_waiting_queue_rejects_without_reading_or_consuming_another_slot(self):
        for _ in range(2):
            self.slots.acquire()
            self.waiters.semaphore.acquire()
        try:
            with self.assertRaises(AsIsError) as caught:
                self.service.observe(daemon_keys=['osd.0'])
            self.assertEqual((caught.exception.code, caught.exception.status), ('COLLECTION_BUSY', 429))
            self.assertEqual(self.client.calls, [])
        finally:
            for _ in range(2):
                self.slots.release()
                self.waiters.semaphore.release()
        self.service.observe(daemon_keys=['osd.0'])
        self.assert_slots_reusable()

    def test_wait_timeout_releases_waiting_capacity_and_does_not_read(self):
        for _ in range(2):
            self.slots.acquire()
        try:
            with self.assertRaises(AsIsError) as caught:
                self.service.observe(daemon_keys=['osd.0'])
            self.assertEqual((caught.exception.code, caught.exception.status), ('COLLECTION_BUSY', 429))
            self.assertEqual(self.client.calls, [])
            self.assertTrue(self.waiters.semaphore.acquire(blocking=False))
            self.assertTrue(self.waiters.semaphore.acquire(blocking=False))
            self.waiters.semaphore.release()
            self.waiters.semaphore.release()
        finally:
            for _ in range(2):
                self.slots.release()
        self.service.observe(daemon_keys=['osd.0'])
        self.assert_slots_reusable()

    def test_source_errors_and_interrupts_release_running_capacity(self):
        for error in (
            ExecutorClientError('EXECUTOR_UNAVAILABLE', 'private detail'),
            AsIsError('FSID_MISMATCH', 'different cluster'),
            RuntimeError('source crashed'),
            KeyboardInterrupt(),
        ):
            with self.subTest(error=type(error).__name__), \
                 patch.object(self.service, '_observe', side_effect=error):
                expected = AsIsError if isinstance(error, ExecutorClientError) else type(error)
                with self.assertRaises(expected) as caught:
                    self.service.observe(daemon_keys=['osd.0'])
                if isinstance(error, ExecutorClientError):
                    self.assertEqual(caught.exception.status, 503)
                    self.assertNotIn('private detail', str(caught.exception))
            self.assert_slots_reusable()

    def test_scope_validation_precedes_queue_admission(self):
        with self.assertRaises(AsIsError) as caught:
            self.service.observe(daemon_keys=['osd.5'])
        self.assertEqual(caught.exception.code, 'DAEMON_SCOPE_REJECTED')
        self.assertFalse(self.waiters.admitted.is_set())
        self.assertEqual(self.client.calls, [])
        self.assert_slots_reusable()


if __name__ == '__main__':
    unittest.main()
