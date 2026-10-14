"""One-shot, read-only operations probe; never restart services or delete data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from production_acceptance import AcceptanceError, Client, canonical_bytes, load_accounts, utc_now


PROJECT = re.compile(r'^storage-lab-console-(?:production|staging)[a-z0-9_-]{0,64}$')
VOLUME_TARGETS = (
    ('postgres', 'postgres-data', '/var/lib/postgresql/data', True),
    ('api', 'evidence', '/var/lib/storage-lab-console/evidence', True),
    ('executor', 'executor-state', '/var/lib/rbd-executor', False),
)


def deployment_identity(directory: Path) -> tuple[str, int]:
    if not (directory / 'compose.production.yml').is_file():
        raise AcceptanceError('PRODUCTION_COMPOSE_REQUIRED')
    values = {}
    for line in (directory / '.env').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([A-Z0-9_]+)=([^\r\n]*)', line)
        if match:
            if match[1] in values:
                raise AcceptanceError('DUPLICATE_RUNTIME_KEY')
            values[match[1]] = match[2]
    project = values.get('COMPOSE_PROJECT_NAME', '')
    if not PROJECT.fullmatch(project) or values.get('APP_INSTANCE_ID') != project:
        raise AcceptanceError('EXPLICIT_PRODUCTION_OR_STAGING_ID_REQUIRED')
    port = int(values.get('CONSOLE_HTTPS_PORT', '8443'))
    if not 1024 <= port <= 65535:
        raise AcceptanceError('INVALID_HTTPS_PORT')
    return project, port


def run_docker(arguments: list[str]) -> str:
    try:
        result = subprocess.run(['docker', *arguments], capture_output=True, text=True,
                                timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise AcceptanceError('DOCKER_UNAVAILABLE') from None
    if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
        raise AcceptanceError('DOCKER_OPERATION_FAILED')
    return result.stdout


def deployment_containers(project: str) -> list[dict]:
    if not PROJECT.fullmatch(project):
        raise AcceptanceError('EXPLICIT_PRODUCTION_OR_STAGING_ID_REQUIRED')
    ids = run_docker(['ps', '-aq', '--filter', f'label=com.docker.compose.project={project}']).split()
    if (not ids or len(ids) > 128 or len(ids) != len(set(ids))
            or any(not re.fullmatch(r'[a-f0-9]{12,64}', item) for item in ids)):
        raise AcceptanceError('DEPLOYMENT_CONTAINERS_MISSING')
    rows = json.loads(run_docker(['inspect', *ids]))
    if not isinstance(rows, list) or len(rows) != len(ids):
        raise AcceptanceError('CONTAINER_INSPECTION_INVALID')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('Config'), dict)
                or not isinstance(row.get('State'), dict)):
            raise AcceptanceError('CONTAINER_INSPECTION_INVALID')
        labels = row['Config'].get('Labels') or {}
        identity = row.get('Id', '')
        if (not isinstance(labels, dict) or not isinstance(identity, str)
                or labels.get('com.docker.compose.project') != project
                or not re.fullmatch(r'[a-f0-9]{64}', identity)
                or len([item for item in ids if identity.startswith(item)]) != 1
                or identity in seen):
            raise AcceptanceError('CONTAINER_PROJECT_OR_ID_MISMATCH')
        seen.add(identity)
        if (not isinstance(labels.get('com.docker.compose.service'), str)
                or not isinstance(row['State'].get('Health', {}), dict)):
            raise AcceptanceError('CONTAINER_INSPECTION_INVALID')
    if any(len([identity for identity in seen if identity.startswith(item)]) != 1 for item in ids):
        raise AcceptanceError('CONTAINER_PROJECT_OR_ID_MISMATCH')
    return rows


def container_checks(project: str) -> dict:
    states = []
    for row in deployment_containers(project):
        labels = row['Config']['Labels']
        service = labels.get('com.docker.compose.service', 'unknown')
        state = row['State']; finished_job = service in {'migrate', 'database-permissions'}
        good = (state.get('ExitCode') == 0 and state.get('Status') == 'exited') if finished_job else (
            state.get('Running') and not state.get('OOMKilled') and
            state.get('Health', {}).get('Status', 'healthy') == 'healthy')
        states.append({'service': service, 'state': state.get('Status'),
                       'health': state.get('Health', {}).get('Status'),
                       'oom_killed': bool(state.get('OOMKilled')), 'healthy': bool(good)})
    if not {'api', 'postgres', 'ingress'} <= {row['service'] for row in states}:
        raise AcceptanceError('BUNDLED_PRODUCTION_SERVICES_MISSING')
    return {'services': states, 'healthy': all(row['healthy'] for row in states)}


def parse_filesystem_usage(output: str) -> dict:
    """Parse only POSIX df -Pk output, never treat missing output as zero use."""
    lines = [line for line in output.splitlines() if line.strip()]
    if len(output) > 8192 or len(lines) != 2 or not lines[0].startswith('Filesystem'):
        raise AcceptanceError('VOLUME_DISK_OUTPUT_INVALID')
    fields = lines[1].split()
    if (len(fields) != 6 or not all(re.fullmatch(r'\d+', item) for item in fields[1:4])
            or not re.fullmatch(r'\d{1,3}%', fields[4]) or not fields[5].startswith('/')):
        raise AcceptanceError('VOLUME_DISK_OUTPUT_INVALID')
    total, used, available = (int(item) * 1024 for item in fields[1:4])
    percent = int(fields[4][:-1])
    if (total <= 0 or total > 2**64 - 1 or used > total or available > total
            or used + available > total or percent > 100):
        raise AcceptanceError('VOLUME_DISK_OUTPUT_INVALID')
    # BusyBox and GNU df differ on reserved space and rounding. Check the
    # reported percentage against either convention, then use the conservative
    # available-space ratio for alerting; never silently accept e.g. 900/100
    # blocks with a reported 1% as healthy. KiB display rounding allows 1pp.
    usable = used + available
    if usable <= 0:
        raise AcceptanceError('VOLUME_DISK_OUTPUT_INVALID')
    raw_ratio = 100 * used / total
    usable_ratio = 100 * used / usable
    if min(abs(percent - raw_ratio), abs(percent - usable_ratio)) > 1:
        raise AcceptanceError('VOLUME_DISK_OUTPUT_INVALID')
    conservative_percent = max(percent, (100 * used + usable - 1) // usable)
    return {'total_bytes': total, 'used_bytes': used, 'available_bytes': available,
            'used_percent': conservative_percent, 'reported_used_percent': percent,
            'alert_calculation': 'MAX_REPORTED_AND_CEILING_USED_OVER_USED_PLUS_AVAILABLE'}


def volume_disk_checks(project: str, alert_percent: float) -> dict:
    """Read df through exact, project-verified container/volume identities."""
    containers = deployment_containers(project)
    checks = []
    for service, volume_key, target, required in VOLUME_TARGETS:
        item = {'service': service, 'volume': volume_key, 'path': target,
                'alert_percent': alert_percent}
        checks.append(item)
        candidates = [row for row in containers
                      if (row['Config'].get('Labels') or {}).get('com.docker.compose.service') == service]
        if not candidates and not required:
            item.update(status='NOT_RUN', reason='OPTIONAL_SERVICE_NOT_DEPLOYED')
            continue
        try:
            if len(candidates) != 1:
                raise AcceptanceError('VOLUME_SERVICE_MISSING_OR_AMBIGUOUS')
            row = candidates[0]
            if not row.get('State', {}).get('Running'):
                raise AcceptanceError('VOLUME_SERVICE_NOT_RUNNING')
            mounts = [mount for mount in row.get('Mounts', []) if mount.get('Destination') == target]
            if (len(mounts) != 1 or mounts[0].get('Type') != 'volume'
                    or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,255}', mounts[0].get('Name', ''))):
                raise AcceptanceError('EXPECTED_NAMED_VOLUME_NOT_MOUNTED')
            name = mounts[0]['Name']
            volumes = json.loads(run_docker(['volume', 'inspect', name]))
            if not isinstance(volumes, list) or len(volumes) != 1 or volumes[0].get('Name') != name:
                raise AcceptanceError('VOLUME_INSPECTION_INVALID')
            labels = volumes[0].get('Labels') or {}
            if (labels.get('com.docker.compose.project') != project
                    or labels.get('com.docker.compose.volume') != volume_key):
                raise AcceptanceError('VOLUME_PROJECT_OR_ROLE_MISMATCH')
            # No shell, sudo, writes, dynamic paths, or name-based exec. The
            # full immutable container ID cannot redirect to a replacement.
            usage = parse_filesystem_usage(run_docker(['exec', row['Id'], 'df', '-Pk', target]))
            item.update(usage, status='HIGH' if usage['used_percent'] >= alert_percent else 'PASS',
                        observed_at=utc_now())
        except (AcceptanceError, ValueError, TypeError, KeyError, AttributeError) as exc:
            item.update(status='UNAVAILABLE', reason=str(exc) if isinstance(exc, AcceptanceError)
                        else 'VOLUME_DISK_OUTPUT_INVALID')
    return {'volumes': checks, 'healthy': all(item['status'] in {'PASS', 'NOT_RUN'} for item in checks),
            'measurement': 'FILESYSTEM_CONTAINING_VERIFIED_MOUNT_NOT_PER_VOLUME_QUOTA',
            'does_not_measure_backing_host_or_volume_quota': True,
            'shared_filesystem_values_must_not_be_summed': True}


def backup_age(root: Path, maximum_hours: float, expected_project: str | None = None) -> dict:
    latest = None
    for directory in root.glob('backup-*'):
        path = directory / 'backup-metadata.json'
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            continue
        try:
            row = json.loads(path.read_bytes())
            if (not isinstance(row, dict) or row.get('status') != 'COMPLETE' or row.get('format_version') != 1
                    or (expected_project is not None and row.get('source_project') != expected_project)
                    or not isinstance(row.get('started_at'), str)):
                continue
            # started_at is conservative: completed_at is not a data checkpoint.
            # PowerShell emits Z and seven fractional digits. Python 3.10
            # accepts +00:00 and at most six digits; conservatively discard
            # sub-microsecond precision, never a timezone or whole second.
            iso = row['started_at'].replace('Z', '+00:00')
            iso = re.sub(r'(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)', r'\1', iso)
            stamp = datetime.fromisoformat(iso)
            if stamp.tzinfo is None:
                continue
            latest = max(latest, stamp) if latest else stamp
        except (KeyError, ValueError, OSError):
            continue
    age = (datetime.now(timezone.utc) - latest).total_seconds() / 3600 if latest else None
    return {'checkpoint_age_hours': round(age, 4) if age is not None else None,
            'maximum_age_hours': maximum_hours, 'healthy': age is not None and 0 <= age <= maximum_hours,
            'source_project_verified': expected_project is not None and latest is not None,
            'archive_integrity_and_restore_not_checked_by_this_age_probe': True,
            'rpo_is_not_measured_by_backup_age_alone': True}


def host_disk_check(path: Path, alert_percent: float) -> dict:
    try:
        if not path.is_dir():
            raise OSError('Storage directory unavailable')
        usage = shutil.disk_usage(path)
        if usage.total <= 0 or not 0 <= usage.used <= usage.total:
            raise OSError('Disk usage unavailable')
        percent = 100 * usage.used / usage.total
        return {'path': str(path.resolve()), 'used_percent': round(percent, 2),
                'available_bytes': usage.free, 'alert_percent': alert_percent,
                'status': 'HIGH' if percent >= alert_percent else 'PASS',
                'does_not_measure_docker_vm_disk': True}
    except OSError:
        return {'status': 'UNAVAILABLE', 'reason': 'HOST_STORAGE_PATH_UNAVAILABLE',
                'alert_percent': alert_percent}


def main(argv=None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('--deployment-directory', required=True, type=Path)
    command.add_argument('--ca-file', required=True, type=Path)
    command.add_argument('--auth-user-file', required=True, type=Path)
    command.add_argument('--backup-root', required=True, type=Path)
    command.add_argument('--max-backup-age-hours', type=float, default=26)
    command.add_argument('--disk-alert-percent', type=float, default=85)
    command.add_argument('--host-storage-path', action='append', type=Path, default=[],
                         help='Additional existing storage directory, e.g. Docker Desktop virtual-disk parent')
    command.add_argument('--daemon-key', action='append', default=[])
    command.add_argument('--report', required=True, type=Path)
    args = command.parse_args(argv)
    started = time.monotonic()
    report = {'kind': 'PRODUCTION_OPERATIONS_PROBE', 'checked_at': utc_now(),
              'thresholds_status': 'PROPOSED_NOT_APPROVED', 'not_a_production_signoff': True,
              'alerts': [], 'checks': {}}
    try:
        if not 0 < args.disk_alert_percent < 100 or not 0 < args.max_backup_age_hours <= 168:
            raise AcceptanceError('INVALID_OPERATIONS_THRESHOLDS')
        if len(args.host_storage_path) > 8:
            raise AcceptanceError('TOO_MANY_HOST_STORAGE_PATHS')
        if len(args.daemon_key) > 2 or any(not re.fullmatch(r'(mon|mgr|osd|rgw|mds)\.[A-Za-z0-9_.-]{1,128}', key) for key in args.daemon_key):
            raise AcceptanceError('FRESH_PROBE_REQUIRES_ZERO_TO_TWO_EXPLICIT_DAEMONS')
        project, port = deployment_identity(args.deployment_directory)
        accounts = load_accounts(args.auth_user_file, None, None, 'viewer')
        client = Client(f'https://localhost:{port}', args.ca_file, 90)
        runtime = client.request('GET', '/api/runtime-config', accounts['viewer'])
        report['checks']['runtime'] = runtime.summary()
        if runtime.status != 200 or runtime.json().get('environment') != 'production' or runtime.json().get('deployment_id') != project:
            raise AcceptanceError('RUNTIME_IDENTITY_NOT_VERIFIED')
        report['checks']['containers'] = container_checks(project)
        if not report['checks']['containers']['healthy']:
            report['alerts'].append('CONTAINER_UNHEALTHY')
        ready = client.request('GET', '/api/ready', accounts['viewer'])
        report['checks']['ready'] = ready.summary()
        if ready.status != 200:
            report['alerts'].append('DEPENDENCY_NOT_READY')
        report['checks']['host_disk'] = host_disk_check(args.deployment_directory, args.disk_alert_percent)
        report['checks']['backup_host_disk'] = host_disk_check(args.backup_root, args.disk_alert_percent)
        report['checks']['additional_host_disks'] = [host_disk_check(path, args.disk_alert_percent)
                                                     for path in args.host_storage_path]
        host_disks = [report['checks']['host_disk'], report['checks']['backup_host_disk'],
                      *report['checks']['additional_host_disks']]
        if any(item['status'] == 'HIGH' for item in host_disks):
            report['alerts'].append('HOST_DISK_HIGH')
        if any(item['status'] == 'UNAVAILABLE' for item in host_disks):
            report['alerts'].append('HOST_STORAGE_PATH_UNAVAILABLE')
        report['checks']['volume_disks'] = volume_disk_checks(project, args.disk_alert_percent)
        disks = report['checks']['volume_disks']['volumes']
        if any(item['status'] == 'HIGH' for item in disks):
            report['alerts'].append('VOLUME_FILESYSTEM_DISK_HIGH')
        if any(item['status'] == 'UNAVAILABLE' for item in disks):
            report['alerts'].append('VOLUME_FILESYSTEM_DISK_UNAVAILABLE')
        report['checks']['backup'] = backup_age(args.backup_root, args.max_backup_age_hours, project)
        if not report['checks']['backup']['healthy']:
            report['alerts'].append('BACKUP_MISSING_STALE_OR_CLOCK_INVALID')
        if args.daemon_key:
            fresh = client.request('POST', '/api/v1/as-is/observe', accounts['viewer'], {'daemon_keys': args.daemon_key, 'deep': False})
            report['checks']['fresh_read'] = fresh.summary()
            if fresh.status != 200:
                report['alerts'].append('FRESH_COLLECTION_FAILED')
            else:
                source = fresh.json().get('sources', {}).get('prometheus', {})
                report['checks']['metric_source'] = {key: source.get(key) for key in ('quality', 'reason', 'http_status', 'window_seconds', 'identity_binding')}
                if source.get('quality') != 'VALID':
                    report['alerts'].append('METRIC_SOURCE_NOT_VALID')
    except (AcceptanceError, OSError, ValueError) as exc:
        report['alerts'].append(str(exc) if isinstance(exc, AcceptanceError) else 'OPERATIONS_CONFIGURATION_FAILED')
    report.update(status='ALERT' if report['alerts'] else 'PASS', duration_seconds=round(time.monotonic()-started, 3))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(canonical_bytes(report) + b'\n')
    print(json.dumps({'status': report['status'], 'alerts': report['alerts'], 'report': str(args.report)}))
    return 2 if report['alerts'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
