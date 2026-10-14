"""Deliver redacted operations alerts to one explicitly configured receiver.

Standard library only. No proxy, redirects, dynamic destination, scheduler,
service restart, or collection writes. The receiver must acknowledge with 2xx.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import stat
import tempfile
import threading
import time
from urllib.parse import urlsplit


MAX_JSON_BYTES = 1024 * 1024
MAX_RESPONSE_HEADER_BYTES = 8192
MAX_RESPONSE_BYTES = 1024
MAX_PAYLOAD_BYTES = 8192
MAX_REPORT_AGE_SECONDS = 600
CODE = re.compile(r'[A-Z][A-Z0-9_]{0,95}\Z')
HASH = re.compile(r'[a-f0-9]{64}\Z')
REPORT_KINDS = {'PRODUCTION_OPERATIONS_PROBE', 'PRODUCTION_MAINTENANCE_BACKUP'}


class AlertError(Exception):
    """A stable code only: never an endpoint, path, token, or remote body."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AlertError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read_file(path: Path, limit: int, *, private: bool = False) -> bytes:
    try:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_size > limit:
            raise AlertError('INPUT_FILE_INVALID')
        # Windows host ACLs must be restricted by the administrator. POSIX
        # file mode enforcement is possible without third-party libraries.
        if private and os.name != 'nt' and details.st_mode & 0o077:
            raise AlertError('PRIVATE_FILE_PERMISSIONS_REQUIRED')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as handle:
            current = os.fstat(handle.fileno())
            if (not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != (details.st_dev, details.st_ino)):
                raise AlertError('INPUT_FILE_CHANGED')
            value = handle.read(limit + 1)
        if len(value) > limit:
            raise AlertError('INPUT_FILE_TOO_LARGE')
        return value
    except OSError:
        raise AlertError('INPUT_FILE_UNAVAILABLE') from None


def read_json(path: Path, *, private: bool = False) -> dict:
    def reject_constant(value):
        raise AlertError('INPUT_JSON_NON_FINITE')
    try:
        value = json.loads(read_file(path, MAX_JSON_BYTES, private=private),
                           object_pairs_hook=_unique_object, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise AlertError('INPUT_JSON_INVALID') from None
    if not isinstance(value, dict):
        raise AlertError('INPUT_JSON_OBJECT_REQUIRED')
    return value


def _timestamp(value) -> str:
    if not isinstance(value, str) or len(value) > 48:
        raise AlertError('REPORT_TIMESTAMP_INVALID')
    try:
        iso = value.replace('Z', '+00:00')
        iso = re.sub(r'(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)', r'\1', iso)
        parsed = datetime.fromisoformat(iso)
        if parsed.tzinfo is None:
            raise ValueError
        parsed = parsed.astimezone(timezone.utc)
        age = (datetime.now(timezone.utc) - parsed).total_seconds()
        if age < -60 or age > MAX_REPORT_AGE_SECONDS:
            raise AlertError('REPORT_STALE_OR_CLOCK_INVALID')
        return parsed.isoformat()
    except (ValueError, OverflowError):
        raise AlertError('REPORT_TIMESTAMP_INVALID') from None


def redacted_report(report: dict) -> dict:
    if not isinstance(report.get('kind'), str) or report['kind'] not in REPORT_KINDS:
        raise AlertError('OPERATIONS_REPORT_REQUIRED')
    status = report.get('status')
    alerts = report.get('alerts')
    thresholds = report.get('thresholds_status')
    if (not isinstance(status, str) or status not in {'PASS', 'ALERT'} or not isinstance(alerts, list)
            or len(alerts) > 64 or any(not isinstance(code, str) or not CODE.fullmatch(code) for code in alerts)
            or (status == 'PASS' and alerts) or (status == 'ALERT' and not alerts)
            or not isinstance(thresholds, str) or thresholds not in {'PROPOSED_NOT_APPROVED', 'APPROVED'}):
        raise AlertError('OPERATIONS_REPORT_INVALID')
    return {'kind': report['kind'], 'status': status,
            'alerts': sorted(set(alerts)), 'checked_at': _timestamp(report.get('checked_at')),
            'thresholds_proposed': thresholds != 'APPROVED'}


def parse_endpoint(value: str, allow_loopback_test: bool) -> dict:
    if (not isinstance(value, str) or len(value) > 2048 or not value.isascii()
            or any(ord(char) <= 32 or ord(char) == 127 for char in value) or '\\' in value):
        raise AlertError('ENDPOINT_INVALID')
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise AlertError('ENDPOINT_INVALID') from None
    if (parsed.scheme not in {'https', 'http'} or not host or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or '?' in value or '#' in value or '%' in host
            or not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}', host)):
        raise AlertError('ENDPOINT_INVALID')
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == 'localhost'
    if parsed.scheme == 'http' and not (allow_loopback_test and loopback):
        raise AlertError('HTTPS_REQUIRED')
    port = port if port is not None else (443 if parsed.scheme == 'https' else 80)
    if not 1 <= port <= 65535:
        raise AlertError('ENDPOINT_INVALID')
    authority = '[' + host.lower() + ']' if ':' in host else host.lower()
    if port != (443 if parsed.scheme == 'https' else 80):
        authority += ':' + str(port)
    return {'scheme': parsed.scheme, 'host': host.lower(), 'port': port,
            'path': parsed.path or '/', 'origin': parsed.scheme + '://' + authority,
            'production_transport': parsed.scheme == 'https'}


def load_config(path: Path, allow_loopback_test: bool) -> dict:
    value = read_json(path, private=True)
    allowed = {'format_version', 'endpoint', 'allowed_origin', 'bearer_token_file',
               'ca_file', 'timeout_seconds'}
    if (set(value) - allowed or type(value.get('format_version')) is not int
            or value.get('format_version') != 1):
        raise AlertError('DELIVERY_CONFIGURATION_INVALID')
    target = parse_endpoint(value.get('endpoint'), allow_loopback_test)
    if value.get('allowed_origin') != target['origin']:
        raise AlertError('ENDPOINT_ORIGIN_NOT_ALLOWLISTED')
    timeout = value.get('timeout_seconds', 5)
    if (isinstance(timeout, bool) or not isinstance(timeout, (float, int))
            or not math.isfinite(timeout) or not 0.1 <= timeout <= 10):
        raise AlertError('DELIVERY_TIMEOUT_INVALID')
    target['timeout_seconds'] = float(timeout)
    target['target_hash'] = hashlib.sha256(value['endpoint'].encode('ascii')).hexdigest()
    target['bearer'] = None
    for key in ('bearer_token_file', 'ca_file'):
        if key not in value:
            continue
        name = value[key]
        if not isinstance(name, str) or not name or len(name) > 4096 or '\x00' in name:
            raise AlertError('DELIVERY_CONFIGURATION_INVALID')
        file_path = Path(name)
        if not file_path.is_absolute():
            file_path = path.parent / file_path
        if key == 'bearer_token_file':
            token_bytes = read_file(file_path, 8192, private=True)
            try:
                token = token_bytes.decode('ascii').rstrip('\r\n')
            except UnicodeError:
                raise AlertError('BEARER_TOKEN_INVALID') from None
            if not token or len(token) > 8192 or any(not 33 <= ord(char) <= 126 for char in token):
                raise AlertError('BEARER_TOKEN_INVALID')
            target['bearer'] = token
        else:
            # Validate a regular, bounded public CA file before ssl reads it.
            read_file(file_path, MAX_JSON_BYTES)
            target['ca_file'] = str(file_path)
    try:
        target['ssl_context'] = ssl.create_default_context(cafile=target.get('ca_file'))
        target['ssl_context'].minimum_version = ssl.TLSVersion.TLSv1_2
    except (OSError, ssl.SSLError):
        raise AlertError('TLS_CONFIGURATION_INVALID') from None
    return target


def _resolved_addresses(host: str, port: int, deadline: float) -> list:
    """Do not let unbounded system DNS block the CLI's network deadline."""
    output = queue.Queue(maxsize=1)
    def resolve():
        try:
            output.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except OSError:
            output.put(None)
    threading.Thread(target=resolve, daemon=True).start()
    try:
        rows = output.get(timeout=max(0.001, deadline - time.monotonic()))
    except queue.Empty:
        raise AlertError('DELIVERY_TIMEOUT') from None
    if not isinstance(rows, list) or not rows or len(rows) > 32:
        raise AlertError('DNS_RESOLUTION_FAILED')
    return rows


class _HeaderBoundedFile:
    """Cap status/header/trailer lines without replacing stdlib HTTP parsing."""
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.remaining = MAX_RESPONSE_HEADER_BYTES

    def readline(self, limit=-1):
        size = self.remaining + 1 if limit < 0 else min(limit, self.remaining + 1)
        value = self.wrapped.readline(size)
        self.remaining -= len(value)
        if self.remaining < 0:
            raise AlertError('RESPONSE_HEADERS_TOO_LARGE')
        return value

    def __getattr__(self, name):
        return getattr(self.wrapped, name)


class _BoundedHTTPResponse(http.client.HTTPResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fp = _HeaderBoundedFile(self.fp)


def send_webhook(config: dict, payload: dict) -> int:
    """Direct HTTP(S), fixed destination, bounded DNS/total time/body size."""
    data = canonical_bytes(payload)
    if len(data) > MAX_PAYLOAD_BYTES:
        raise AlertError('DELIVERY_PAYLOAD_TOO_LARGE')
    deadline = time.monotonic() + config['timeout_seconds']
    sockets = []
    response_holder = []
    expired = threading.Event()
    if config['scheme'] == 'https':
        connection = http.client.HTTPSConnection(config['host'], config['port'],
                                                 timeout=config['timeout_seconds'],
                                                 context=config['ssl_context'])
    else:
        connection = http.client.HTTPConnection(config['host'], config['port'],
                                                timeout=config['timeout_seconds'])
    connection.response_class = _BoundedHTTPResponse

    def create_connection(address, timeout=None, source_address=None):
        if address != (config['host'], config['port']) or source_address is not None:
            raise AlertError('UNCONFIGURED_DESTINATION_REFUSED')
        rows = _resolved_addresses(config['host'], config['port'], deadline)
        if config['scheme'] == 'http' and any(not ipaddress.ip_address(row[4][0]).is_loopback for row in rows):
            raise AlertError('LOOPBACK_RESOLUTION_REQUIRED')
        for family, sock_type, protocol, _, destination in rows:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or expired.is_set():
                raise AlertError('DELIVERY_TIMEOUT')
            stream = socket.socket(family, sock_type, protocol)
            sockets.append(stream)
            try:
                stream.settimeout(remaining)
                stream.connect(destination)
                if expired.is_set() or time.monotonic() >= deadline:
                    stream.close()
                    raise AlertError('DELIVERY_TIMEOUT')
                return stream
            except OSError:
                stream.close()
        raise AlertError('DELIVERY_CONNECTION_FAILED')

    # HTTPConnection uses this factory for its sole configured destination.
    # This does not consult urllib/environment proxies or perform another DNS
    # lookup after the validated, deadline-bounded resolution above.
    connection._create_connection = create_connection

    def abort():
        expired.set()
        current = [*sockets, connection.sock]
        if response_holder:
            raw = getattr(getattr(response_holder[0].fp, 'raw', None), '_sock', None)
            current.append(raw)
        for stream in current:
            if stream is not None:
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    stream.close()
                except OSError:
                    pass

    timer = threading.Timer(config['timeout_seconds'], abort)
    timer.daemon = True
    timer.start()
    response = None
    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                   'User-Agent': 'Storage-Lab-Console-Alert/1',
                   'Idempotency-Key': payload['event_id']}
        if config['bearer']:
            headers['Authorization'] = 'Bearer ' + config['bearer']
        connection.request('POST', config['path'], body=data, headers=headers)
        response = connection.getresponse()
        response_holder.append(response)
        status = response.status
        if not 100 <= status <= 599:
            raise AlertError('HTTP_STATUS_INVALID')
        if 300 <= status < 400:
            raise AlertError('HTTP_REDIRECT_REFUSED')
        size = response.getheader('Content-Length')
        if size is not None and (not re.fullmatch(r'\d{1,10}', size) or int(size) > MAX_RESPONSE_BYTES):
            raise AlertError('RESPONSE_SIZE_INVALID_OR_TOO_LARGE')
        observed = 0
        while observed <= MAX_RESPONSE_BYTES:
            if expired.is_set() or time.monotonic() >= deadline:
                raise AlertError('DELIVERY_TIMEOUT')
            chunk = response.read1(min(256, MAX_RESPONSE_BYTES + 1 - observed))
            if not chunk:
                break
            observed += len(chunk)
        if observed > MAX_RESPONSE_BYTES:
            raise AlertError('RESPONSE_TOO_LARGE')
        if not 200 <= status < 300:
            error = AlertError('HTTP_STATUS_REJECTED')
            error.http_status = status
            raise error
        if expired.is_set() or time.monotonic() >= deadline:
            raise AlertError('DELIVERY_TIMEOUT')
        return status
    except AlertError as error:
        if response is not None:
            error.http_status = response.status
        raise
    except ssl.SSLCertVerificationError:
        raise AlertError('TLS_VERIFICATION_FAILED') from None
    except (socket.timeout, TimeoutError):
        raise AlertError('DELIVERY_TIMEOUT') from None
    except (OSError, http.client.HTTPException, ValueError):
        raise AlertError('DELIVERY_TIMEOUT' if expired.is_set() else 'DELIVERY_CONNECTION_FAILED') from None
    finally:
        timer.cancel()
        if response is not None:
            response.close()
        connection.close()


@contextmanager
def state_lock(path: Path):
    """Kernel lock releases after a crash; never steal/remove another lock."""
    handle = None
    locked = False
    try:
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise AlertError('STATE_LOCK_INVALID')
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        handle = os.fdopen(descriptor, 'r+b', buffering=0)
        if os.fstat(descriptor).st_size == 0:
            handle.write(b'\0')
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    except OSError:
        raise AlertError('STATE_LOCK_BUSY_OR_UNAVAILABLE') from None
    finally:
        if handle is not None:
            if locked:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def load_state(path: Path, target_hash: str, report_kind: str) -> dict:
    if not path.exists() and not path.is_symlink():
        return {'format_version': 1, 'target_hash': target_hash, 'report_kind': report_kind, 'generation': 0,
                'last_delivered_status': None, 'last_delivered_fingerprint': None}
    state = read_json(path, private=True)
    if (set(state) - {'format_version', 'target_hash', 'report_kind', 'generation', 'last_delivered_status',
                      'last_delivered_fingerprint', 'updated_at'}
            or type(state.get('format_version')) is not int or state.get('format_version') != 1
            or state.get('target_hash') != target_hash):
        raise AlertError('STATE_FORMAT_OR_TARGET_MISMATCH')
    if state.get('report_kind') != report_kind:
        raise AlertError('STATE_REPORT_KIND_MISMATCH')
    generation = state.get('generation')
    if (isinstance(generation, bool) or not isinstance(generation, int) or not 1 <= generation < 2**53
            or not isinstance(state.get('last_delivered_status'), str)
            or state.get('last_delivered_status') not in {'PASS', 'ALERT'}
            or not isinstance(state.get('last_delivered_fingerprint'), str)
            or not HASH.fullmatch(state['last_delivered_fingerprint'])):
        raise AlertError('STATE_INVALID')
    return state


def commit_state(path: Path, state: dict) -> None:
    temporary = None
    try:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise AlertError('STATE_COMMIT_FAILED')
        descriptor, temporary = tempfile.mkstemp(prefix='.alert-state-', dir=path.parent)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(canonical_bytes(state) + b'\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except OSError:
        raise AlertError('STATE_COMMIT_FAILED') from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def deliver(report: dict, config: dict, state_path: Path, test_delivery: bool) -> dict:
    redacted = redacted_report(report)
    fingerprint = hashlib.sha256(canonical_bytes({key: value for key, value in redacted.items()
                                                  if key != 'checked_at'})).hexdigest()
    with state_lock(state_path.with_name(state_path.name + '.lock')):
        state = load_state(state_path, config['target_hash'], redacted['kind'])
        if state['generation'] >= 2**53 - 1:
            raise AlertError('STATE_GENERATION_EXHAUSTED')
        if test_delivery:
            event = 'TEST'
        elif redacted['status'] == 'PASS':
            if state['last_delivered_status'] != 'ALERT':
                return {'status': 'SKIPPED_PASS', 'event': None, 'http_status': None}
            event = 'RECOVERY'
        elif state['last_delivered_fingerprint'] == fingerprint:
            return {'status': 'SKIPPED_DUPLICATE', 'event': None, 'http_status': None}
        else:
            event = 'ALERT'
        event_id = hashlib.sha256(canonical_bytes({'target_hash': config['target_hash'], 'event': event,
                                                   'fingerprint': fingerprint,
                                                   'generation': state['generation'] + 1})).hexdigest()
        payload = {**redacted, 'event': event, 'event_id': event_id,
                   'test_delivery': test_delivery,
                   'production_transport': config['production_transport']}
        try:
            http_status = send_webhook(config, payload)
        except AlertError as error:
            error.event = event
            raise
        if not test_delivery:
            try:
                commit_state(state_path, {'format_version': 1, 'target_hash': config['target_hash'],
                                         'report_kind': redacted['kind'],
                                         'generation': state['generation'] + 1,
                                         'last_delivered_status': redacted['status'],
                                         'last_delivered_fingerprint': fingerprint,
                                         'updated_at': utc_now()})
            except AlertError as error:
                error.http_status = http_status
                error.delivery_completed = True
                error.event = event
                raise
        return {'status': 'DELIVERED', 'event': event, 'http_status': http_status,
                'delivery_completed': True, 'state_committed': not test_delivery}


def main(argv=None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('--config', required=True, type=Path)
    command.add_argument('--report', required=True, type=Path)
    command.add_argument('--state', required=True, type=Path)
    command.add_argument('--receipt', required=True, type=Path)
    command.add_argument('--test-delivery', action='store_true',
                         help='Explicit TEST notification; never alter alert/recovery dedup state')
    command.add_argument('--allow-loopback-test', action='store_true',
                         help='Permit HTTP to verified loopback only; not production transport')
    args = command.parse_args(argv)
    started = time.monotonic()
    receipt = {'format_version': 1, 'kind': 'PRODUCTION_ALERT_DELIVERY_RECEIPT',
               'checked_at': utc_now(), 'status': 'FAILED', 'event': None,
               'http_status': None, 'reason': None, 'delivery_completed': False,
               'not_a_production_signoff': True, 'production_transport': None}
    descriptor = None
    try:
        # Reserve the create-only receipt BEFORE sending any network request.
        descriptor = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        if len({os.path.normcase(str(path.absolute())) for path in
                (args.config, args.report, args.state, args.receipt)}) != 4:
            raise AlertError('INPUT_AND_OUTPUT_PATHS_MUST_DIFFER')
        if not args.state.parent.is_dir():
            raise AlertError('STATE_DIRECTORY_REQUIRED')
        config = load_config(args.config, args.allow_loopback_test)
        receipt['production_transport'] = config['production_transport']
        receipt.update(deliver(read_json(args.report), config, args.state, args.test_delivery))
    except FileExistsError:
        receipt['reason'] = 'RECEIPT_ALREADY_EXISTS'
    except AlertError as error:
        receipt.update(reason=str(error), http_status=getattr(error, 'http_status', None),
                       delivery_completed=getattr(error, 'delivery_completed', False),
                       event=getattr(error, 'event', None))
    except OSError:
        receipt['reason'] = 'DELIVERY_LOCAL_STORAGE_UNAVAILABLE'
    receipt['duration_seconds'] = round(time.monotonic() - started, 3)
    if descriptor is not None:
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(canonical_bytes(receipt) + b'\n')
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            receipt.update(status='FAILED', reason='RECEIPT_WRITE_FAILED')
    # No endpoint, filename, credentials, body, or raw exception in stdout.
    print(canonical_bytes({key: receipt.get(key) for key in
                           ('status', 'event', 'http_status', 'reason', 'delivery_completed')}).decode('ascii'))
    return 2 if receipt['status'] == 'FAILED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
