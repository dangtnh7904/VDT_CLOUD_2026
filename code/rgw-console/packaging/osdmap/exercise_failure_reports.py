"""Deliberately fail the isolated integration to verify its failure reports.

Opt-in modes affect only the synthetic in-process source/client. The real
offline worker is used for the corrupt-map case. Never run against live data.
"""
from contextlib import ExitStack
import base64
import hashlib
import os
from unittest.mock import patch

import test_api_worker_integration as runner


def main():
    runner.require(os.environ.get('OSDMAP_SYNTHETIC_TEST') == '1', 'SYNTHETIC_OPT_IN_REQUIRED')
    runner.validate_database_url(os.environ.get('DATABASE_URL'))
    runner.require(not os.environ.get('DATABASE_URL_FILE'), 'EXPLICIT_ISOLATED_DATABASE_REQUIRED')
    fault = os.environ.get('OSDMAP_SYNTHETIC_REPORT_TEST_FAULT')
    runner.require(fault in ('capability-stale', 'corrupt-map', 'transport', 'invalid-json'),
                   'UNKNOWN_SYNTHETIC_REPORT_TEST_FAULT')
    from app.config import get_settings
    runner.validate_database_url(get_settings().database_url)
    from app.modules.osdmap_preview.service import PreviewService
    from starlette.testclient import TestClient
    import httpx

    state = {'create_count': 0, 'injected': False}
    original_run = runner.run
    original_create = PreviewService.create
    original_capability = PreviewService.capabilities
    original_source = runner.SyntheticClient.request
    original_request = TestClient.request

    def tagged_run(args, report, diagnostics=None):
        report['deliberate_failure_test'] = fault
        try:
            return original_run(args, report, diagnostics)
        finally:
            report['deliberate_fault_executed'] = state['injected']

    def counted_create(service, *args, **kwargs):
        state['create_count'] += 1
        return original_create(service, *args, **kwargs)

    def capability(service):
        if fault == 'capability-stale' and state['create_count'] == 1:
            state['injected'] = True
            return {'available': False, 'code': 'OSDMAP_CAPABILITIES_STALE', 'reason': 'Synthetic control'}
        return original_capability(service)

    def source(client, action, **kwargs):
        response = original_source(client, action, **kwargs)
        if fault == 'corrupt-map' and action == 'ceph.osd_map_export':
            state['injected'] = True
            raw = b'GENERATED_SYNTHETIC_INVALID_MAP_FOR_FAILURE_REPORT_TEST'
            response['data'] = {'map': base64.b64encode(raw).decode(),
                                'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}
        return response

    def request(client, method, url, *args, **kwargs):
        headers = kwargs.get('headers') or {}
        valid_create = method.upper() == 'POST' and str(url) == runner.API_ROOT \
            and headers.get('X-Console-Request') == '1' and not headers.get('Origin')
        if valid_create and fault in ('transport', 'invalid-json'):
            state['injected'] = True
            if fault == 'transport':
                raise ConnectionError('SYNTHETIC_PASSWORD_MUST_NOT_APPEAR_IN_REPORT')
            return httpx.Response(502, text='SYNTHETIC_PASSWORD_MUST_NOT_APPEAR_IN_REPORT',
                                  request=httpx.Request(method, 'http://synthetic.test' + str(url)))
        return original_request(client, method, url, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(runner, 'run', tagged_run))
        stack.enter_context(patch.object(PreviewService, 'create', counted_create))
        stack.enter_context(patch.object(PreviewService, 'capabilities', capability))
        stack.enter_context(patch.object(runner.SyntheticClient, 'request', source))
        stack.enter_context(patch.object(TestClient, 'request', request))
        return runner.main()


if __name__ == '__main__':
    raise SystemExit(main())
