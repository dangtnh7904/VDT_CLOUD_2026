"""Replay the SHA-verified historical test behind today's strict DB guard.

Adds bounded stage diagnostics in the runner only. Does not change the API,
worker, historical source, fixtures, or any live deployment.
"""
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import time
from unittest.mock import patch

from test_api_worker_integration import require, validate_database_url


HISTORICAL_SHA256 = 'ea523c81ae3da14450c14471a5a1dcac80c1c2fd8d354969840cb3e06bd7cefb'


def main():
    require(os.environ.get('OSDMAP_SYNTHETIC_TEST') == '1', 'SYNTHETIC_OPT_IN_REQUIRED')
    validate_database_url(os.environ.get('DATABASE_URL'))
    require(not os.environ.get('DATABASE_URL_FILE'), 'EXPLICIT_ISOLATED_DATABASE_REQUIRED')
    fault = os.environ.get('OSDMAP_SYNTHETIC_DIAGNOSTIC_FAULT', 'none')
    require(fault in ('none', 'capability-stale', 'worker-tool-failed', 'result-read-oserror'),
            'UNKNOWN_SYNTHETIC_DIAGNOSTIC_FAULT')
    trace_mode = os.environ.get('OSDMAP_SYNTHETIC_DIAGNOSTIC_TRACE', '1')
    require(trace_mode in ('0', '1') and (trace_mode == '1' or fault == 'none'),
            'UNKNOWN_SYNTHETIC_DIAGNOSTIC_TRACE_MODE')
    historical = Path('/forensics/historical_script.py')
    require(hashlib.sha256(historical.read_bytes()).hexdigest() == HISTORICAL_SHA256,
            'HISTORICAL_SOURCE_HASH_MISMATCH')
    from app.config import get_settings
    validate_database_url(get_settings().database_url)
    from app.modules.osdmap_preview.service import PreviewService
    from starlette.testclient import TestClient
    namespace = runpy.run_path(str(historical))
    entry = namespace['main']
    globals_for_run = entry.__globals__
    historical_run = globals_for_run['run']

    def diagnose(args, report):
        report['historical_source_sha256'] = HISTORICAL_SHA256
        report['diagnostics_added_only_in_external_runner'] = True
        report['synthetic_fault_control'] = fault
        report['stage_tracing_enabled'] = trace_mode == '1'
        if trace_mode == '0':
            return historical_run(args, report)
        traces = report['request_trace'] = []
        active = [None]
        original_create = PreviewService.create
        original_capability = PreviewService.capabilities
        original_decode = PreviewService._worker_result
        original_validate = PreviewService._validate_result_identity
        original_post = TestClient.post
        responses = report['http_post_responses'] = []

        def traced_post(client, *values, **kwargs):
            response = original_post(client, *values, **kwargs)
            code = None
            if response.status_code >= 400:
                detail = response.json().get('detail')
                candidate = detail.get('code') if isinstance(detail, dict) else None
                if isinstance(candidate, str) and len(candidate) <= 128 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in candidate):
                    code = candidate
            responses.append({'status_code': response.status_code, 'code': code})
            return response

        def traced_create(service, *values, **kwargs):
            trace = {'sequence': len(traces) + 1, 'capability': None,
                     'worker_envelope_received': False, 'worker_success_decoded': False,
                     'identity_validation_entered': False, 'returned_successfully': False}
            traces.append(trace)
            active[0] = trace
            began = time.monotonic()
            try:
                result = original_create(service, *values, **kwargs)
                trace['returned_successfully'] = True
                return result
            except Exception as exc:
                trace['exception_type'] = type(exc).__name__
                # Only stable bounded codes/errno, never exception text or SQL/config.
                code = getattr(exc, 'code', None)
                if isinstance(code, str) and len(code) <= 128 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in code):
                    trace['exception_code'] = code
                status = getattr(exc, 'status', None)
                if type(status) is int:
                    trace['exception_status'] = status
                if isinstance(exc, OSError):
                    trace['errno'] = exc.errno
                raise
            finally:
                trace['duration_seconds'] = time.monotonic() - began
                active[0] = None

        def traced_capability(service):
            value = original_capability(service)
            trace = active[0]
            if trace is not None:
                if trace['sequence'] == 7 and fault == 'capability-stale':
                    value = {'available': False, 'code': 'OSDMAP_CAPABILITIES_STALE',
                             'reason': 'Explicit synthetic fault control'}
                trace['capability'] = {'available': value.get('available'), 'code': value.get('code')}
                path = service.settings.osdmap_preview_spool / 'capabilities.json'
                try:
                    if not path.is_symlink() and path.stat().st_size <= 4096:
                        raw = json.loads(path.read_text())
                        heartbeat = raw.get('heartbeat')
                        if type(heartbeat) in (int, float) and math.isfinite(heartbeat):
                            trace['heartbeat_age_seconds_after_check'] = time.time() - heartbeat
                except (OSError, ValueError):
                    trace['heartbeat_diagnostic_unavailable'] = True
            return value

        def traced_decode(output):
            trace = active[0]
            if trace is not None:
                if trace['sequence'] == 7 and fault == 'worker-tool-failed':
                    output = {'ok': False, 'code': 'OSDMAP_TOOL_FAILED'}
                if trace['sequence'] == 7 and fault == 'result-read-oserror':
                    raise OSError(5, 'Explicit synthetic fault control')
                trace['worker_envelope_received'] = True
                trace['worker_envelope'] = {key: output.get(key) for key in ('ok', 'code')} if isinstance(output, dict) else {'type': type(output).__name__}
            result = original_decode(output)
            if trace is not None:
                trace['worker_success_decoded'] = True
            return result

        def traced_validate(result, capability, pool_id):
            trace = active[0]
            if trace is not None:
                trace['identity_validation_entered'] = True
                trace['result_tool_hashes_match_capability'] = isinstance(result, dict) and result.get('tool_binary_sha256') == capability.get('tool_binary_sha256')
            return original_validate(result, capability, pool_id)

        with ExitStack() as stack:
            stack.enter_context(patch.object(PreviewService, 'create', traced_create))
            stack.enter_context(patch.object(PreviewService, 'capabilities', traced_capability))
            stack.enter_context(patch.object(PreviewService, '_worker_result', staticmethod(traced_decode)))
            stack.enter_context(patch.object(PreviewService, '_validate_result_identity', staticmethod(traced_validate)))
            stack.enter_context(patch.object(TestClient, 'post', traced_post))
            historical_run(args, report)

    globals_for_run['run'] = diagnose
    return entry()


if __name__ == '__main__':
    raise SystemExit(main())
