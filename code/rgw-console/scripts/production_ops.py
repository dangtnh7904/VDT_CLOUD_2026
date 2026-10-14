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


def container_checks(project: str) -> dict:
    ids = run_docker(['ps', '-aq', '--filter', f'label=com.docker.compose.project={project}']).split()
    if not ids or any(not re.fullmatch(r'[a-f0-9]{12,64}', item) for item in ids):
        raise AcceptanceError('DEPLOYMENT_CONTAINERS_MISSING')
    rows = json.loads(run_docker(['inspect', *ids]))
    states = []
    for row in rows:
        labels = row['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.project') != project:
            raise AcceptanceError('CONTAINER_PROJECT_MISMATCH')
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


def backup_age(root: Path, maximum_hours: float) -> dict:
    latest = None
    for directory in root.glob('backup-*'):
        path = directory / 'backup-metadata.json'
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            continue
        try:
            row = json.loads(path.read_bytes())
            if (not isinstance(row, dict) or row.get('status') != 'COMPLETE'
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
            'rpo_is_not_measured_by_backup_age_alone': True}


def main(argv=None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('--deployment-directory', required=True, type=Path)
    command.add_argument('--ca-file', required=True, type=Path)
    command.add_argument('--auth-user-file', required=True, type=Path)
    command.add_argument('--backup-root', required=True, type=Path)
    command.add_argument('--max-backup-age-hours', type=float, default=26)
    command.add_argument('--disk-alert-percent', type=float, default=85)
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
        usage = shutil.disk_usage(args.deployment_directory)
        percent = 100 * usage.used / usage.total
        report['checks']['host_disk'] = {'used_percent': round(percent, 2), 'alert_percent': args.disk_alert_percent,
                                        'does_not_measure_docker_vm_disk': True}
        if percent >= args.disk_alert_percent:
            report['alerts'].append('HOST_DISK_HIGH')
        report['checks']['backup'] = backup_age(args.backup_root, args.max_backup_age_hours)
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
