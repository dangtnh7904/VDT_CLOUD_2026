#!/usr/bin/python3
"""OpenSSH forced command for the Console's collection-only Ceph account.

Install as root with Python isolated mode (-I). This does not grant privileges:
all commands run as the dedicated SSH account, with an explicit read-only CephX
identity. No shell, sudo, caller-supplied executable/path, or caller environment
is used to execute the original SSH command.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


POLICY_PATH = Path('/etc/storage-lab-console/ssh-readonly.json')
HELPER_PATH = Path('/opt/storage-lab/collect_osd.py')
CEPH_BINARY = '/usr/bin/ceph'
CEPH_NAME = 'client.storage-lab-console'
CEPH_KEYRING = Path('/etc/storage-lab-console/ceph.client.storage-lab-console.keyring')
CEPH_CONF = Path('/etc/storage-lab-console/ceph.conf')
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SELECTED_OSDS = 16
MAX_COMMAND_BYTES = 8192
MAX_OPERATION_SECONDS = 300
SAFE_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'SHELL': '/bin/sh'}

# Keep these exact argv in step with executor.js. Do not replace this with a
# prefix such as `ceph *`, a regular-expression shell command, or a sudo rule.
DIRECT_READS = frozenset({
    ('fsid',),
    ('status', '--format=json'),
    ('versions', '--format=json'),
    ('fs', 'dump', '--format=json'),
    ('osd', 'dump', '--format=json'),
    ('osd', 'df', '--format=json'),
    ('osd', 'tree', '--format=json'),
    ('osd', 'pool', 'ls', 'detail', '--format=json'),
    ('osd', 'crush', 'dump', '--format=json'),
    ('osd', 'crush', 'rule', 'dump', '--format=json'),
    ('pg', 'dump', 'pgs_brief', '--format=json'),
    ('mon', 'dump', '--format=json'),
    ('quorum_status', '--format=json'),
    ('mgr', 'dump', '--format=json'),
    ('mgr', 'module', 'ls', '--format=json'),
    ('mgr', 'services', '--format=json'),
    ('orch', 'ps', '--refresh', '--format=json'),
    ('orch', 'host', 'ls', '--format=json'),
    ('health', 'detail', '--format=json'),
    ('df', 'detail', '--format=json'),
})
HELPER_COMMON_READS = frozenset({
    ('pg', 'stat', '--format=json'),
    ('osd', 'df', 'tree', '--format=json'),
    ('config', 'dump', '--format=json'),
})
ENVIRONMENT_PROBES = {
    ('rbd', '--version'): ('/usr/bin/rbd', '--version'),
    ('rados', '--version'): ('/usr/bin/rados', '--version'),
    ('ssh', '-V'): ('/usr/bin/ssh', '-V'),
    ('osdmaptool', '--version'): ('/usr/bin/osdmaptool', '--version'),
    ('crushtool', '--version'): ('/usr/bin/crushtool', '--version'),
    ('timedatectl', 'show', '--property=NTP', '--property=NTPSynchronized', '--property=Timezone', '--property=LocalRTC'):
        ('/usr/bin/timedatectl', 'show', '--property=NTP', '--property=NTPSynchronized', '--property=Timezone', '--property=LocalRTC'),
}


class Rejected(RuntimeError):
    """Only authored codes may be written to the SSH error stream."""


@dataclass(frozen=True)
class Policy:
    expected_fsid: str
    allowed_osds: frozenset[int]
    collector_sha256: str


@dataclass(frozen=True)
class Plan:
    kind: str
    args: tuple[str, ...] = ()
    osd_ids: tuple[int, ...] = ()
    timeout: float = 45


def validate_policy(raw) -> Policy:
    if not isinstance(raw, dict) or set(raw) != {'expected_fsid', 'allowed_osds', 'collector_sha256'}:
        raise Rejected('SSH_POLICY_INVALID')
    try:
        fsid = str(UUID(raw['expected_fsid']))
    except (ValueError, TypeError, AttributeError):
        raise Rejected('SSH_POLICY_INVALID') from None
    ids = raw['allowed_osds']
    checksum = raw['collector_sha256']
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 128
        or any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2147483647 for value in ids)
        or len(set(ids)) != len(ids) or not isinstance(checksum, str)
        or re.fullmatch('[a-f0-9]{64}', checksum) is None):
        raise Rejected('SSH_POLICY_INVALID')
    return Policy(fsid, frozenset(ids), checksum)


def trusted_file(path: Path, *, maximum: int | None = None) -> bytes:
    """Reject symlinks and non-root/writable policy or executable parents."""
    try:
        if not path.is_absolute():
            raise Rejected('SSH_INSTALLATION_UNTRUSTED')
        for candidate in [path, *path.parents]:
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise Rejected('SSH_INSTALLATION_UNTRUSTED')
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or maximum is not None and info.st_size > maximum:
            raise Rejected('SSH_INSTALLATION_UNTRUSTED')
        if maximum is not None:
            with path.open('rb') as handle:
                result = handle.read(maximum + 1)
            if len(result) > maximum:
                raise Rejected('SSH_INSTALLATION_UNTRUSTED')
            return result
        return b''
    except OSError:
        raise Rejected('SSH_INSTALLATION_UNTRUSTED') from None


def parse_command(original: str, policy: Policy) -> Plan:
    if (not isinstance(original, str) or not original or len(original.encode('utf-8')) > MAX_COMMAND_BYTES
        or re.fullmatch(r'[A-Za-z0-9_./:= -]+', original) is None):
        raise Rejected('SSH_COMMAND_REJECTED')
    parts = original.split(' ')
    if any(not part for part in parts):
        raise Rejected('SSH_COMMAND_REJECTED')
    # Compatibility with the existing executor's transport framing. Never
    # execute sudo; discard exactly this framing before matching fixed argv.
    if parts[:2] == ['sudo', '-n']:
        parts = parts[2:]
    if parts and parts[0] == 'ceph' and tuple(parts[1:]) in DIRECT_READS:
        return Plan('ceph', tuple(parts[1:]))
    if parts[:2] != ['python3', HELPER_PATH.as_posix()]:
        raise Rejected('SSH_COMMAND_REJECTED')
    args = parts[2:]
    if args in (['--environment-only', '--timeout', '2'], ['--environment-only', '--sudo-ceph', '--timeout', '2']):
        return Plan('environment', timeout=2)
    selected = []
    while len(args) >= 2 and args[0] == '--osd':
        if re.fullmatch(r'0|[1-9][0-9]{0,9}', args[1]) is None:
            raise Rejected('SSH_COMMAND_REJECTED')
        value = int(args[1])
        if value not in policy.allowed_osds or value in selected or len(selected) >= MAX_SELECTED_OSDS:
            raise Rejected('SSH_OSD_SCOPE_REJECTED')
        selected.append(value)
        args = args[2:]
    if args[:1] == ['--sudo-ceph']:
        args = args[1:]
    if not selected or len(args) != 2 or args[0] != '--timeout' or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', args[1]) is None:
        raise Rejected('SSH_COMMAND_REJECTED')
    timeout = float(args[1])
    if not 0 < timeout <= 45:
        raise Rejected('SSH_TIMEOUT_REJECTED')
    return Plan('collect', osd_ids=tuple(selected), timeout=timeout)


def ceph_prefix() -> tuple[str, ...]:
    return (CEPH_BINARY, '--name', CEPH_NAME, '--keyring', str(CEPH_KEYRING), '--conf', str(CEPH_CONF))


def helper_read_allowed(args: tuple[str, ...], selected: tuple[int, ...]) -> bool:
    if args in DIRECT_READS or args in HELPER_COMMON_READS:
        return True
    for osd_id in selected:
        number, daemon = str(osd_id), f'osd.{osd_id}'
        if args in {
            ('osd', 'metadata', number, '--format=json'),
            ('osd', 'find', number, '--format=json'),
            ('pg', 'ls-by-osd', daemon, '--format=json'),
            ('pg', 'ls-by-primary', daemon, '--format=json'),
            ('config', 'show-with-defaults', daemon, '--format=json'),
            ('device', 'ls-by-daemon', daemon, '--format=json'),
        }:
            return True
    return False


class BoundedRunner:
    def __init__(self, *, timeout=MAX_OPERATION_SECONDS):
        self.deadline = time.monotonic() + timeout
        self.remaining = MAX_TOTAL_SOURCE_BYTES
        self.cancelled = threading.Event()
        self.active = {}
        self.active_lock = threading.RLock()

    def cancel(self):
        self.cancelled.set()
        with self.active_lock:
            for process in self.active.values():
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def run(self, args, *, timeout=45, maximum=MAX_OUTPUT_BYTES):
        if self.cancelled.is_set():
            raise Rejected('SSH_COLLECTION_CANCELLED')
        remaining_time = self.deadline - time.monotonic()
        if remaining_time <= 0:
            raise Rejected('SSH_COLLECTION_TIMEOUT')
        maximum = min(maximum, self.remaining)
        if maximum <= 0:
            raise Rejected('SSH_SOURCE_OUTPUT_LIMIT')
        try:
            process = subprocess.Popen(list(args), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                cwd='/', env=SAFE_ENV, start_new_session=True)
        except OSError:
            raise Rejected('SSH_EXECUTION_FAILED') from None
        with self.active_lock:
            self.active[process.pid] = process
        outputs = [bytearray(), bytearray()]
        overflow = threading.Event()

        def drain(pipe, target, limit):
            try:
                while True:
                    chunk = pipe.read(4096)
                    if not chunk:
                        break
                    if len(target) + len(chunk) > limit:
                        overflow.set()
                    target.extend(chunk[:max(0, limit - len(target))])
            finally:
                pipe.close()

        readers = [threading.Thread(target=drain, args=(process.stdout, outputs[0], maximum), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, outputs[1], min(65536, maximum)), daemon=True)]
        for reader in readers:
            reader.start()
        end = time.monotonic() + min(timeout, remaining_time)
        error = None
        while process.poll() is None:
            if overflow.is_set() or self.cancelled.is_set() or time.monotonic() >= end:
                error = ('SSH_COLLECTION_CANCELLED' if self.cancelled.is_set() else
                    'SSH_SOURCE_OUTPUT_LIMIT' if overflow.is_set() else 'SSH_COLLECTION_TIMEOUT')
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                break
            time.sleep(0.01)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.cancel()
            raise Rejected('SSH_COLLECTION_TIMEOUT') from None
        finally:
            with self.active_lock:
                self.active.pop(process.pid, None)
        for reader in readers:
            reader.join(timeout=0.5)
        if self.cancelled.is_set():
            raise Rejected('SSH_COLLECTION_CANCELLED')
        if error or overflow.is_set() or any(reader.is_alive() for reader in readers):
            raise Rejected(error or 'SSH_SOURCE_OUTPUT_LIMIT')
        self.remaining -= sum(map(len, outputs))
        return process.returncode, bytes(outputs[0])

    def evidence(self, args, *, timeout, maximum=MAX_OUTPUT_BYTES):
        started = datetime.now(timezone.utc).isoformat()
        code, output = self.run(args, timeout=timeout, maximum=maximum)
        try:
            text = output.decode('utf-8').strip()
        except UnicodeDecodeError:
            raise Rejected('SSH_SOURCE_ENCODING_INVALID') from None
        try:
            data, form = json.loads(text), 'json'
        except ValueError:
            data, form = text, 'text'
        result = {'command': list(args), 'started_at': started, 'completed_at': datetime.now(timezone.utc).isoformat(),
            'exit_code': code, 'stderr': '', 'data': data, 'format': form}
        if code:
            result['error'] = 'COMMAND_FAILED'
        return result


def check_fsid(policy: Policy, runner: BoundedRunner):
    code, result = runner.run((*ceph_prefix(), 'fsid'), timeout=10, maximum=8192)
    if code:
        raise Rejected('SSH_FSID_READ_FAILED')
    try:
        observed = str(UUID(result.decode('utf-8').strip()))
    except (ValueError, UnicodeDecodeError):
        raise Rejected('SSH_FSID_INVALID') from None
    if observed != policy.expected_fsid:
        raise Rejected('SSH_FSID_MISMATCH')


def load_helper(policy: Policy):
    source = trusted_file(HELPER_PATH, maximum=1024 * 1024)
    if hashlib.sha256(source).hexdigest() != policy.collector_sha256:
        raise Rejected('SSH_COLLECTOR_CHECKSUM_MISMATCH')
    spec = importlib.util.spec_from_file_location('_storage_lab_readonly_collector', HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(plan: Plan, policy: Policy, runner: BoundedRunner):
    check_fsid(policy, runner)
    if plan.kind == 'ceph':
        code, output = runner.run((*ceph_prefix(), *plan.args))
        if code:
            raise Rejected('SSH_CEPH_COMMAND_FAILED')
    else:
        helper = load_helper(policy)
        prefix = ceph_prefix()
        failures = []

        def guarded_read(command):
            try:
                parts = tuple(command)
                if parts[:len(prefix)] != prefix or not helper_read_allowed(parts[len(prefix):], plan.osd_ids):
                    raise Rejected('SSH_HELPER_COMMAND_REJECTED')
                return runner.evidence(parts, timeout=plan.timeout)
            except Rejected as exc:
                failures.append(str(exc))
                raise

        def guarded_environment(command):
            try:
                parts = tuple(command)
                if parts == (*prefix, '--version'):
                    target = parts
                else:
                    target = ENVIRONMENT_PROBES.get(parts)
                if target is None:
                    raise Rejected('SSH_HELPER_COMMAND_REJECTED')
                return runner.evidence(target, timeout=2, maximum=8192)
            except Rejected as exc:
                failures.append(str(exc))
                raise

        try:
            if plan.kind == 'collect':
                payload = helper.collect(osd_ids=plan.osd_ids, ceph_bin=prefix[0], ceph_args=prefix[1:], runner=guarded_read)
                if payload.get('cluster_fsid') != policy.expected_fsid:
                    raise Rejected('SSH_FSID_MISMATCH')
            elif plan.kind == 'environment':
                payload = helper.collect_environment(ceph_command=prefix, runner=guarded_environment)
            else:
                raise Rejected('SSH_COMMAND_REJECTED')
        except Exception:
            if failures:
                raise Rejected(failures[0]) from None
            raise
        # The legacy helper intentionally catches per-command failures. A guard
        # rejection/timeout must not be converted into a successful partial run.
        if failures:
            raise Rejected(failures[0])
        output = (json.dumps(payload, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    check_fsid(policy, runner)
    if len(output) > MAX_OUTPUT_BYTES:
        raise Rejected('SSH_EXPORT_OUTPUT_LIMIT')
    return output


def main():
    try:
        if os.geteuid() == 0:
            raise Rejected('SSH_ROOT_ACCOUNT_REJECTED')
        # No arguments may override the fixed policy or original command.
        if len(sys.argv) != 1:
            raise Rejected('SSH_COMMAND_REJECTED')
        trusted_file(Path(__file__).absolute())
        policy = validate_policy(json.loads(trusted_file(POLICY_PATH, maximum=16384)))
        trusted_file(CEPH_KEYRING)
        if CEPH_KEYRING.lstat().st_mode & (stat.S_IROTH | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            raise Rejected('SSH_KEYRING_PERMISSIONS_INVALID')
        trusted_file(CEPH_CONF)
        trusted_file(Path(CEPH_BINARY))
        plan = parse_command(os.environ.get('SSH_ORIGINAL_COMMAND', ''), policy)
        os.environ.clear()
        os.environ.update(SAFE_ENV)
        runner = BoundedRunner()
        for number in (signal.SIGHUP, signal.SIGTERM):
            signal.signal(number, lambda *_: runner.cancel())
        sys.stdout.buffer.write(execute(plan, policy, runner))
        return 0
    except Rejected as exc:
        print(str(exc), file=sys.stderr)
        return 126
    except Exception:
        print('SSH_DISPATCH_FAILED', file=sys.stderr)
        return 126


if __name__ == '__main__':
    raise SystemExit(main())
