import unittest
from unittest.mock import Mock, patch

from app.modules.as_is.service import AsIsError, CollectionControl, wait_for_metric_window
from app.services.executor_client import ExecutorClient
import httpx
import json
from datetime import datetime, timedelta, timezone
from app.services.performance import counter_sample, PerformanceTelemetryError


class MetricWindowTests(unittest.TestCase):
    def test_counter_rate_can_use_monotonic_window_not_wall_clock_jump(self):
        start = datetime.now(timezone.utc)
        old = {'read_ops': 100, 'write_ops': 100, 'read_bytes': 100, 'write_bytes': 100}
        new = {key: value + 30 for key, value in old.items()}
        sample = counter_sample(fsid='f', scope_type='osd', scope_id='0', captured_at=start+timedelta(seconds=315),
            counters=new, previous_counters=old, previous_captured_at=start, metric_names={}, elapsed_seconds=15)
        self.assertEqual(sample.read_iops, 2)
        self.assertEqual(sample.window_seconds, 15)
        for window in (0, -1, float('nan'), float('inf')):
            with self.subTest(window=window), self.assertRaises(PerformanceTelemetryError):
                counter_sample(fsid='f', scope_type='osd', scope_id='0', captured_at=start,
                    counters=new, previous_counters=old, previous_captured_at=start, metric_names={}, elapsed_seconds=window)

    def test_wait_is_bounded_by_configured_exporter_window(self):
        control = Mock()
        with patch('app.modules.as_is.service.monotonic_time.monotonic', side_effect=[100, 105, 115]):
            wait_for_metric_window(control, 100, 15)
        self.assertEqual(control.cancelled.wait.call_count, 2)
        self.assertEqual(control.check.call_count, 3)
        self.assertTrue(all(call.args[0] <= .1 for call in control.cancelled.wait.call_args_list))

    def test_cancel_interrupts_window_without_new_scrape(self):
        control = CollectionControl()
        control.cancel()
        with self.assertRaises(AsIsError) as caught:
            wait_for_metric_window(control, 100, 15)
        self.assertEqual(caught.exception.code, 'COLLECTION_CANCELLED')

    def test_expired_request_does_not_wait(self):
        control = CollectionControl(timeout_seconds=-1)
        with self.assertRaises(AsIsError) as caught:
            wait_for_metric_window(control, 100, 15)
        self.assertEqual(caught.exception.code, 'COLLECTION_TIMEOUT')

    def test_python_client_accepts_fixed_mgr_services_and_enforces_fsid(self):
        fsid = '11111111-2222-3333-4444-555555555555'
        def response(request):
            body = json.loads(request.content)
            self.assertEqual(body['action'], 'ceph.mgr_services')
            return httpx.Response(200, json={'version': 1, 'request_id': body['request_id'], 'ok': True,
                'result': {'action': body['action'], 'fsid': fsid, 'collected_at': '2026-10-14T00:00:00Z',
                           'data': {'prometheus': 'http://mgr.invalid:9283/'}}})
        client = ExecutorClient('http://executor:3001', token='test-executor-token-with-more-than-32-characters',
                                expected_fsid=fsid, transport=httpx.MockTransport(response))
        self.assertEqual(client.request('ceph.mgr_services')['fsid'], fsid)


if __name__ == '__main__':
    unittest.main()
