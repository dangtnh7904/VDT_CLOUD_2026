from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import FastAPI, HTTPException

from app.modules.as_is import service as module
from app.modules.as_is.api import _observe_call, ObserveRequest, observe, export_fresh, router
from app.modules.as_is.service import AsIsError, CollectionControl
import test_as_is as fixtures


class CancellationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AsIsTests()
        fixture.setUp()
        self.service, self.client = fixture.service, fixture.client
        self.slots = threading.BoundedSemaphore(2)
        self.waiters = threading.BoundedSemaphore(2)
        for name, value in [('SLOTS', self.slots), ('WAITING_SLOTS', self.waiters)]:
            item = patch.object(module, name, value)
            item.start()
            self.addCleanup(item.stop)

    def test_cancelled_request_never_enters_sources(self):
        control = CollectionControl()
        control.cancel()
        with self.assertRaises(AsIsError) as caught:
            self.service.observe(control=control)
        self.assertEqual(caught.exception.code, 'COLLECTION_CANCELLED')
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.client.identity_calls, 0)

    def test_cancelled_waiter_frees_queue_without_starting_sources(self):
        self.slots.acquire()
        self.slots.acquire()
        control = CollectionControl()
        admitted = threading.Event()
        original_check = control.check

        def checked():
            admitted.set()
            original_check()

        with patch.object(control, 'check', side_effect=checked), ThreadPoolExecutor(max_workers=1) as worker:
            future = worker.submit(self.service.observe, control=control)
            self.assertTrue(admitted.wait(1))
            control.cancel()
            with self.assertRaises(AsIsError) as caught:
                future.result(timeout=1)
        self.assertEqual(caught.exception.code, 'COLLECTION_CANCELLED')
        self.assertEqual(self.client.calls, [])
        self.assertTrue(self.waiters.acquire(blocking=False))
        self.assertTrue(self.waiters.acquire(blocking=False))
        self.waiters.release()
        self.waiters.release()
        self.slots.release()
        self.slots.release()

    def _stopping_inflight(self, deadline=False):
        control = CollectionControl()
        entered = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        calls = []
        original = self.client.request
        self.slots.acquire()  # Only one free collection slot.

        def read(action, **kwargs):
            with lock:
                calls.append(action)
                if len(calls) == 3:
                    entered.set()
            if not release.wait(2):
                raise RuntimeError('test source was not released')
            return original(action, **kwargs)

        with patch.object(self.client, 'request', side_effect=read), ThreadPoolExecutor(max_workers=1) as worker:
            future = worker.submit(self.service.observe, control=control)
            try:
                self.assertTrue(entered.wait(1))
                if deadline:
                    control.deadline = 0
                else:
                    control.cancel()
                self.assertFalse(future.done())
                self.assertFalse(self.slots.acquire(blocking=False), 'in-flight source slot was freed too early')
            finally:
                release.set()
            with self.assertRaises(AsIsError) as caught:
                future.result(timeout=2)
        self.slots.release()
        self.assertEqual(len(calls), 3, 'queued source reads must not execute after cancellation/deadline')
        self.assertEqual(caught.exception.code, 'COLLECTION_TIMEOUT' if deadline else 'COLLECTION_CANCELLED')
        self.assertEqual(self.client.identity_calls, 0, 'final identity read must not start after cancellation')
        self.assertTrue(self.slots.acquire(blocking=False))
        self.assertTrue(self.slots.acquire(blocking=False))
        self.slots.release()
        self.slots.release()
        self.assertEqual(self.service.repository.rows, {})

    def test_cancelled_active_read_stops_pending_sources_but_holds_slot_until_running_reads_settle(self):
        self._stopping_inflight()

    def test_aggregate_deadline_stops_pending_sources_and_retains_slot_until_reads_settle(self):
        self._stopping_inflight(deadline=True)

    def test_expired_deadline_starts_no_sources(self):
        control = CollectionControl(timeout_seconds=0)
        with self.assertRaises(AsIsError) as caught:
            self.service.observe(control=control)
        self.assertEqual((caught.exception.code, caught.exception.status), ('COLLECTION_TIMEOUT', 504))
        self.assertEqual(self.client.calls, [])

    def test_waiting_deadline_does_not_leak_waiter(self):
        self.slots.acquire()
        self.slots.acquire()
        control = CollectionControl(timeout_seconds=0.02)
        with self.assertRaises(AsIsError) as caught:
            self.service.observe(control=control)
        self.assertEqual(caught.exception.code, 'COLLECTION_TIMEOUT')
        self.assertEqual(self.client.calls, [])
        self.assertTrue(self.waiters.acquire(blocking=False))
        self.assertTrue(self.waiters.acquire(blocking=False))
        self.waiters.release()
        self.waiters.release()
        self.slots.release()
        self.slots.release()


class DisconnectWrapperTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_api_deep_budget_uses_configured_collector_timeout_and_shallow_stays_sixty(self):
        class Request:
            async def receive(self):
                await asyncio.Future()

        class Service:
            settings = SimpleNamespace(osd_info_collector_timeout_seconds=213)

            def observe(self, **kwargs):
                remaining = kwargs['control'].deadline - time.monotonic()
                self.test.assertAlmostEqual(remaining, 273 if kwargs['deep'] else 60, delta=1)
                return {'id': 'new-collection'}

        service = Service()
        service.test = self
        for endpoint in (observe, export_fresh):
            for deep in (False, True):
                with self.subTest(endpoint=endpoint.__name__, deep=deep), \
                     patch('app.modules.as_is.api._service', return_value=service):
                    result = await endpoint(ObserveRequest(deep=deep), Request())
                    self.assertIsNotNone(result)

    async def test_actual_asgi_disconnect_reaches_worker_through_base_http_middleware(self):
        entered = threading.Event()
        cancelled = threading.Event()
        messages = asyncio.Queue()
        await messages.put({'type': 'http.request', 'body': b'{}', 'more_body': False})

        class Service:
            def observe(self, **kwargs):
                control = kwargs['control']
                entered.set()
                if control.cancelled.wait(1):
                    cancelled.set()
                control.check()
                return {'unexpected_uncancelled': True}

        app = FastAPI()
        app.include_router(router)

        @app.middleware('http')
        async def identity_middleware(request, call_next):
            return await call_next(request)

        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
            'http_version': '1.1', 'scheme': 'http', 'method': 'POST',
            'path': '/api/v1/as-is/observe', 'raw_path': b'/api/v1/as-is/observe',
            'query_string': b'', 'root_path': '', 'server': ('test', 80),
            'client': ('test', 1234), 'headers': [(b'content-type', b'application/json')]}

        async def send(message):
            pass  # No response-body inspection: the client has disconnected.

        with patch('app.modules.as_is.api._service', return_value=Service()):
            task = asyncio.create_task(app(scope, messages.get, send))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            await messages.put({'type': 'http.disconnect'})
            self.assertTrue(await asyncio.to_thread(cancelled.wait, 1))
            await asyncio.wait_for(task, 2)

    async def test_disconnected_request_cancels_cooperative_worker(self):
        class Request:
            async def receive(self):
                return {'type': 'http.disconnect'}

        def operation(control):
            control.cancelled.wait(1)
            control.check()

        with self.assertRaises(HTTPException) as caught:
            await _observe_call(Request(), operation)
        self.assertEqual(caught.exception.status_code, 499)

    async def test_connected_request_receives_own_fresh_result(self):
        class Request:
            async def receive(self):
                await asyncio.Future()

        result = await _observe_call(Request(), lambda control: {'fresh': True})
        self.assertEqual(result, {'fresh': True})

    async def test_cancelled_asgi_task_signals_running_thread(self):
        entered = threading.Event()
        cancelled = threading.Event()

        class Request:
            async def receive(self):
                await asyncio.Future()

        def operation(control):
            entered.set()
            if control.cancelled.wait(1):
                cancelled.set()
            control.check()

        task = asyncio.create_task(_observe_call(Request(), operation))
        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(await asyncio.to_thread(cancelled.wait, 1))
        await asyncio.sleep(0)


if __name__ == '__main__':
    unittest.main()
