"""Bounded diagnostics for the isolated integration runner, never raw payloads."""
from contextlib import contextmanager, ExitStack
import hashlib
import re
import time
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import UUID


class CheckFailure(RuntimeError):
    pass


def safe_code(value):
    if isinstance(value, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', value):
        return value
    return None


def safe_exception(exc):
    result = {'type': type(exc).__name__[:128]}
    for attribute, field in (('code', 'code'), ('status', 'status'), ('status_code', 'status'), ('errno', 'errno')):
        try:
            value = getattr(exc, attribute, None)
        except Exception:
            continue
        if attribute == 'code':
            code = safe_code(value)
            if code is not None:
                result[field] = code
        elif type(value) is int and (100 <= value <= 599 if field == 'status' else 0 <= value <= 4096):
            result[field] = value
    return result


def safe_stage(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value) else 'UNNAMED_STAGE'


def safe_endpoint(value):
    try:
        path = urlsplit(str(value)).path
    except ValueError:
        return 'REDACTED_ENDPOINT'
    root = '/api/v1/osdmap-previews'
    if path in (root, root + '/capabilities'):
        return path
    if path.startswith(root + '/'):
        components = path[len(root) + 1:].split('/')
        try:
            UUID(components[0])
        except ValueError:
            return 'REDACTED_ENDPOINT'
        if len(components) == 1 or len(components) == 2 and components[1] in ('export', 'apply'):
            return path
    return 'REDACTED_ENDPOINT'


def envelope_summary(output):
    if not isinstance(output, dict):
        return {'type': type(output).__name__}
    ok = output.get('ok')
    code = output.get('code')
    return {'ok': ok if type(ok) is bool else None,
            'ok_type': type(ok).__name__, 'code': safe_code(code),
            'code_rejected': code is not None and safe_code(code) is None}


def write_source_snapshots(directory, sources):
    """Immutable copies of the two runner source files, never runtime config."""
    output = {}
    root = directory / 'sources'
    root.mkdir(parents=True, exist_ok=True)
    for name, content in sources.items():
        digest = hashlib.sha256(content).hexdigest()
        target = root / (digest + '.py')
        if target.exists() or target.is_symlink():
            if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise CheckFailure('SOURCE_SNAPSHOT_CONFLICT')
        else:
            with target.open('xb') as handle:
                handle.write(content)
        output[name] = {'path': 'sources/' + target.name, 'sha256': digest}
    return output


class IntegrationDiagnostics:
    def __init__(self, report):
        self.report = report
        report['diagnostic_schema_version'] = 2
        report['http_requests'] = []
        report['service_requests'] = []
        report['diagnostic_errors'] = []
        report['last_stage'] = 'STARTUP'
        self._http_sequence = 0
        self._service_sequence = 0
        self._active_http = None
        self._active_service = None

    def stage(self, name):
        self.report['last_stage'] = safe_stage(name)

    def _append(self, key, value, limit=512):
        items = self.report[key]
        if len(items) >= limit:
            items.pop(0)
            self.report['diagnostics_truncated'] = True
        items.append(value)

    def request(self, client, stage, method, path, **kwargs):
        self.stage(stage)
        self._http_sequence += 1
        trace = {'sequence': self._http_sequence, 'stage': self.report['last_stage'],
                 'method': method.upper() if method.upper() in ('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS') else 'UNKNOWN',
                 'endpoint': safe_endpoint(path), 'status_code': None, 'code': None}
        self._append('http_requests', trace)
        self.report['last_http'] = trace
        self._active_http = trace
        began = time.monotonic()
        try:
            response = client.request(method, path, **kwargs)
            trace['status_code'] = response.status_code
            if response.status_code >= 400 or trace['endpoint'].endswith('/capabilities'):
                try:
                    if len(response.content) > 65536:
                        trace['error_body_inspection'] = 'SIZE_LIMIT'
                    else:
                        body = response.json()
                        trace['error_json_type'] = type(body).__name__
                        if isinstance(body, dict) and type(body.get('available')) is bool:
                            trace['available'] = body['available']
                        detail = body.get('detail') if isinstance(body, dict) else None
                        candidate = detail.get('code') if isinstance(detail, dict) else body.get('code') if isinstance(body, dict) else None
                        trace['code'] = safe_code(candidate)
                        trace['code_rejected'] = candidate is not None and trace['code'] is None
                except Exception as exc:
                    trace['json_decode_exception'] = safe_exception(exc)
            return response
        except Exception as exc:
            trace['exception'] = safe_exception(exc)
            raise
        finally:
            trace['duration_seconds'] = time.monotonic() - began
            self._active_http = None

    def check(self, name, condition):
        if not condition:
            self.report['failed_check'] = safe_stage(name)
            raise CheckFailure(safe_stage(name))
        self.report['checks'][name] = 'PASS'

    def record_failure(self, exc):
        failure = self.report.get('failed_check')
        if isinstance(exc, CheckFailure):
            failure = failure or safe_code(str(exc)) or 'CHECK_FAILED'
        self.report['failure'] = failure or type(exc).__name__
        http = self.report.get('last_http')
        service = self.report.get('last_service')
        if service is not None and service.get('http_sequence') != (http.get('sequence') if http else None):
            service = None
        capability = self.report.get('last_capability')
        if capability is not None and capability.get('http_sequence') != (http.get('sequence') if http else None):
            capability = None
        self.report['failure_context'] = {
            'stage': self.report['last_stage'], 'failed_check': self.report.get('failed_check'),
            'http': http, 'service': service, 'capability': capability,
            'exception': safe_exception(exc)}

    def _sample(self, snapshot, stage):
        try:
            value = snapshot()
            count, files = value
            return value, {'row_count': count if type(count) is int and count >= 0 else None, 'file_count': len(files)}
        except Exception as exc:
            self._append('diagnostic_errors', {'stage': stage, 'exception': safe_exception(exc)}, 128)
            return None, None

    @contextmanager
    def trace_service(self, service_class, *, source_calls, snapshot):
        original_create = service_class.create
        original_capabilities = service_class.capabilities
        original_decode = service_class._worker_result
        original_validate = service_class._validate_result_identity

        def traced_create(service, *args, **kwargs):
            self._service_sequence += 1
            trace = {'sequence': self._service_sequence, 'stage': self.report['last_stage'],
                     'http_sequence': self._active_http['sequence'] if self._active_http else None,
                     'worker_envelope_received': False, 'worker_success_decoded': False,
                     'identity_validation_entered': False, 'returned_successfully': False,
                     'last_worker_stage': 'CREATE_ENTERED', 'source_calls': [], 'storage_changed': None}
            self._append('service_requests', trace, 128)
            self.report['last_service'] = trace
            self._active_service = trace
            began = time.monotonic()
            before, trace['storage_before'] = self._sample(snapshot, 'storage-before')
            try:
                before_calls = len(source_calls())
            except Exception as exc:
                before_calls = None
                self._append('diagnostic_errors', {'stage': 'source-calls-before', 'exception': safe_exception(exc)}, 128)
            try:
                result = original_create(service, *args, **kwargs)
                trace['returned_successfully'] = True
                return result
            except Exception as exc:
                trace['exception'] = safe_exception(exc)
                raise
            finally:
                after, trace['storage_after'] = self._sample(snapshot, 'storage-after')
                if before is not None and after is not None:
                    try:
                        trace['storage_changed'] = bool(before != after)
                    except Exception as exc:
                        self._append('diagnostic_errors', {'stage': 'storage-compare', 'exception': safe_exception(exc)}, 128)
                try:
                    if before_calls is not None:
                        trace['source_calls'] = [safe_stage(value) for value in source_calls()[before_calls:]][:64]
                except Exception as exc:
                    self._append('diagnostic_errors', {'stage': 'source-calls-after', 'exception': safe_exception(exc)}, 128)
                trace['duration_seconds'] = time.monotonic() - began
                self._active_service = None

        def traced_capabilities(service):
            trace = self._active_service
            if trace is not None:
                trace['last_worker_stage'] = 'CAPABILITY_CHECK'
            result = original_capabilities(service)
            summary = {'available': result.get('available') is True, 'code': safe_code(result.get('code'))} if isinstance(result, dict) else {'type': type(result).__name__}
            summary['http_sequence'] = self._active_http['sequence'] if self._active_http else None
            self.report['last_capability'] = summary
            if trace is not None:
                trace['capability'] = summary
            return result

        def traced_decode(output):
            trace = self._active_service
            if trace is not None:
                trace['last_worker_stage'] = 'WORKER_RESULT_DECODE'
                trace['worker_envelope_received'] = True
                trace['worker_envelope'] = envelope_summary(output)
            result = original_decode(output)
            if trace is not None:
                trace['worker_success_decoded'] = True
            return result

        def traced_validate(result, capability, pool_id):
            trace = self._active_service
            if trace is not None:
                trace['last_worker_stage'] = 'WORKER_IDENTITY_VALIDATION'
                trace['identity_validation_entered'] = True
            return original_validate(result, capability, pool_id)

        with ExitStack() as stack:
            stack.enter_context(patch.object(service_class, 'create', traced_create))
            stack.enter_context(patch.object(service_class, 'capabilities', traced_capabilities))
            stack.enter_context(patch.object(service_class, '_worker_result', staticmethod(traced_decode)))
            stack.enter_context(patch.object(service_class, '_validate_result_identity', staticmethod(traced_validate)))
            yield
