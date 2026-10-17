"""Synthetic API -> real offline worker -> real PostgreSQL/evidence integration.

Run only with OSDMAP_SYNTHETIC_TEST=1 and an explicit isolated DATABASE_URL
or DATABASE_URL_FILE. No executor or live Ceph endpoint is contacted. The
orchestrator starts the migrated PostgreSQL and worker using private volumes.
Test-created rows/artifacts are retained in those disposable volumes as proof;
this script never deletes arbitrary database rows, files or source volumes.
"""
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

from integration_diagnostics import CheckFailure, IntegrationDiagnostics, envelope_summary, safe_exception, write_source_snapshots


CASES = ('no-op', 'multiple-weights')
ALLOWED_ACTIONS = frozenset({'ceph.osdmap_preview_context', 'ceph.osd_dump', 'ceph.osd_map_export'})
API_ROOT = '/api/v1/osdmap-previews'


def require(condition, code):
    if not condition:
        raise CheckFailure(code)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate_database_url(value):
    # libpq accepts query parameters that override the authority/path parsed
    # by urlsplit. This synthetic runner needs none: reject them before app.db
    # can open a pool, along with implicit service/host/options overrides.
    require(isinstance(value, str) and not any(os.environ.get(key) for key in (
        'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE', 'PGUSER',
        'PGSERVICE', 'PGSERVICEFILE', 'PGOPTIONS')),
        'ISOLATED_SYNTHETIC_DATABASE_TARGET_REQUIRED')
    try:
        target = urlsplit(value)
        port = target.port
    except ValueError:
        raise CheckFailure('ISOLATED_SYNTHETIC_DATABASE_TARGET_REQUIRED') from None
    database = unquote(target.path.removeprefix('/'))
    require(target.scheme in ('postgresql', 'postgres') and target.hostname == 'postgres'
            and target.username == 'storage_lab_console' and port in (None, 5432)
            and not target.query and not target.fragment
            and database.startswith('osdmap_synthetic_')
            and all(char in 'abcdefghijklmnopqrstuvwxyz0123456789_' for char in database),
            'ISOLATED_SYNTHETIC_DATABASE_TARGET_REQUIRED')


class SyntheticClient:
    """Closed in-process source adapter; never imports/constructs ExecutorClient."""
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.calls = []
        self.current = CASES[0]
        self.epoch_offset = 0

    def request(self, action, **kwargs):
        if action not in ALLOWED_ACTIONS:
            raise CheckFailure('UNAUTHORIZED_SYNTHETIC_ACTION')
        self.calls.append(action)
        source, metadata = self.fixtures[self.current]
        fsid = metadata['fsid']
        if action == 'ceph.osdmap_preview_context':
            data = {'mons': [{'name': 'generated-fixture-mon', 'osd_crush_update_weight_set': True}],
                    'mon_versions': {metadata['tool_version']: 1}, 'synthetic': True}
        elif action == 'ceph.osd_dump':
            data = {'epoch': metadata['epoch'] + self.epoch_offset, 'pools': deepcopy(metadata['pools'])}
        else:
            raw = base64.b64decode(source['map'], validate=True)
            data = {'encoding': 'base64', 'map': source['map'], 'size_bytes': len(raw),
                    'sha256': source['base_sha256']}
        return {'fsid': fsid, 'data': data}


def load_fixtures(directory):
    fixtures = {}
    hashes = {}
    for name in CASES:
        request_path = directory / (name + '.json')
        metadata_path = directory / (name + '.metadata.json')
        request_bytes, metadata_bytes = request_path.read_bytes(), metadata_path.read_bytes()
        source, metadata = json.loads(request_bytes), json.loads(metadata_bytes)
        require(metadata.get('scope') == 'GENERATED_OFFLINE_FIXTURE_NOT_LIVE_CEPH', 'SYNTHETIC_FIXTURE_SCOPE_REQUIRED')
        raw = base64.b64decode(source['map'], validate=True)
        require(sha256(raw) == source['base_sha256'], 'FIXTURE_MAP_HASH_INVALID')
        require(source['fsid'] == metadata['fsid'], 'FIXTURE_FSID_MISMATCH')
        UUID(metadata['fsid'])
        require(type(metadata['epoch']) is int, 'FIXTURE_EPOCH_INVALID')
        require(isinstance(metadata['pools'], list) and metadata['pools'], 'FIXTURE_POOLS_INVALID')
        require(isinstance(metadata['osds'], list) and metadata['osds'], 'FIXTURE_OSDS_INVALID')
        require(isinstance(metadata['tool_version'], str)
                and metadata['tool_version'].startswith('ceph version 16.2.15 '), 'FIXTURE_TOOL_VERSION_INVALID')
        require(all(type(pool['pool']) is int and isinstance(pool['pool_name'], str)
                    for pool in metadata['pools']), 'FIXTURE_POOL_NAMES_INVALID')
        require(all(type(osd['osd']) is int for osd in metadata['osds']), 'FIXTURE_OSD_IDS_INVALID')
        fixtures[name] = source, metadata
        hashes[name] = {'request_sha256': sha256(request_bytes), 'metadata_sha256': sha256(metadata_bytes),
                        'base_map_sha256': source['base_sha256']}
    require(len({meta['fsid'] for _, meta in fixtures.values()}) == 1, 'FIXTURE_CLUSTERS_DIFFER')
    return fixtures, hashes


def run(args, report, diagnostics=None):
    diagnostics = diagnostics or IntegrationDiagnostics(report)
    diagnostics.stage('validate-synthetic-target')
    require(os.environ.get('OSDMAP_SYNTHETIC_TEST') == '1', 'SYNTHETIC_OPT_IN_REQUIRED')
    require(bool(os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URL_FILE')),
            'EXPLICIT_ISOLATED_DATABASE_REQUIRED')
    configured_url = os.environ.get('DATABASE_URL')
    if os.environ.get('DATABASE_URL_FILE'):
        configured_url = Path(os.environ['DATABASE_URL_FILE']).read_text().strip()
    validate_database_url(configured_url)
    logging.disable(logging.CRITICAL)  # Never include database connection detail in the report/output.
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    from app.config import Settings, get_settings
    runtime_database_url = get_settings().database_url
    validate_database_url(runtime_database_url)
    from app.db import connection, pool
    from app.modules.osdmap_preview import api as routes
    from app.modules.osdmap_preview.service import EXPECTED_TOOL_SHA256, PreviewRepository, PreviewService
    from app.platform.security.middleware import ConsoleSecurityMiddleware

    diagnostics.stage('load-generated-fixtures')
    fixtures, fixture_hashes = load_fixtures(args.fixtures)
    metadata = fixtures['no-op'][1]
    fsid = metadata['fsid']
    cluster_id = 'synthetic-osdmap-' + uuid4().hex[:16]
    report.update({'generated_fsid': fsid, 'cluster_id': cluster_id, 'fixture_hashes': fixture_hashes,
                   'scope': 'SYNTHETIC_GENERATED_MAPS_ONLY_NO_LIVE_CEPH', 'real_worker': True,
                   'real_repository_and_postgresql': True, 'auth': 'disabled_only_for_synthetic_lab',
                   'credentials_in_report': False, 'artifacts': []})
    settings = Settings(_env_file=None, app_env='lab', execution_environment='lab',
        console_read_only=True, console_auth_username='', console_auth_password_hash_file=None,
        console_auth_password_hash=None, feature_upgrade=True, feature_legacy_rgw=False,
        feature_legacy_rbd=False, feature_lab=False, upgrade_mutations_enabled=False,
        cluster_id=cluster_id, cluster_config_path=None, ceph_expected_fsid=fsid,
        database_url=runtime_database_url, database_url_file=None,
        cors_origins='http://synthetic.test', osdmap_preview_spool=args.spool,
        osdmap_preview_timeout_seconds=90, evidence_root=args.evidence,
        upgrade_allowed_osds=','.join(str(osd['osd']) for osd in metadata['osds']),
        upgrade_allowed_pools=','.join(pool['pool_name'] for pool in metadata['pools']))
    active_settings = [settings]
    source_client = SyntheticClient(fixtures)

    def make_service(configured):
        return PreviewService(configured, client=source_client, repository=PreviewRepository())

    def snapshot():
        with connection() as conn:
            count = conn.execute('SELECT count(*) AS count FROM evidence_artifacts WHERE cluster_id=%s AND fsid=%s',
                                 (cluster_id, fsid)).fetchone()['count']
        files = tuple(sorted(str(path.relative_to(args.evidence))
                             for path in (args.evidence / cluster_id).rglob('*.json')))
        return count, files

    def check(name, condition):
        diagnostics.check(name, condition)

    def response_error(response, expected_code):
        return response.status_code == 503 and response.json().get('detail', {}).get('code') == expected_code

    diagnostics.stage('verify-database-schema')
    args.evidence.mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        schema = conn.execute('SELECT max(version) AS version FROM schema_migrations').fetchone()['version']
    check('schema_21', schema == 21)
    report['database_schema'] = schema

    application = FastAPI()
    application.include_router(routes.router)
    application.add_middleware(ConsoleSecurityMiddleware, settings_provider=lambda: settings)
    with patch.object(routes, 'get_settings', side_effect=lambda: active_settings[0]), \
         patch.object(routes, 'PreviewService', side_effect=make_service), \
         diagnostics.trace_service(PreviewService, source_calls=lambda: source_client.calls, snapshot=snapshot), \
         TestClient(application, base_url='http://synthetic.test') as http:
        def request(stage, method, path, **kwargs):
            return diagnostics.request(http, stage, method, path, **kwargs)
        deadline = time.monotonic() + 30
        capability = None
        while time.monotonic() < deadline:
            capability = request('worker-capabilities', 'GET', API_ROOT + '/capabilities').json()
            if capability.get('available') is True:
                break
            time.sleep(0.25)
        check('real_worker_strict_capability', capability is not None and capability.get('available') is True
              and capability.get('parser_version') == 2 and capability.get('pool_types') == ['replicated']
              and capability.get('operations') == ['crush_weight']
              and capability.get('tool_binary_sha256') == EXPECTED_TOOL_SHA256)
        report['worker_identity'] = capability
        header = {'X-Console-Request': '1'}
        initial_body = {'changes': fixtures['no-op'][0]['changes'], 'pool_id': None}
        before_calls = len(source_client.calls)
        check('csrf_missing_header_rejected', request('csrf-missing-header', 'POST', API_ROOT, json=initial_body).status_code == 403)
        check('foreign_origin_rejected', request('foreign-origin', 'POST', API_ROOT, json=initial_body,
              headers={**header, 'Origin': 'https://foreign.invalid'}).status_code == 403)
        check('apply_denied', request('apply-denied', 'POST', API_ROOT + '/' + str(uuid4()) + '/apply',
              json={}, headers=header).status_code in (403, 404))
        check('rejected_http_requests_never_read_sources', len(source_client.calls) == before_calls)

        for name in CASES:
            source_client.current = name
            source_client.epoch_offset = 0
            case_request, case_meta = fixtures[name]
            body = {'changes': case_request['changes'], 'pool_id': case_request.get('pool_id')}
            calls = len(source_client.calls)
            response = request(name + '.create', 'POST', API_ROOT, json=body, headers=header)
            check(name + '_created_201', response.status_code == 201)
            created = response.json()
            identifier = UUID(created['id'])
            check(name + '_fresh_map_and_fixed_reads', created['base_epoch'] == case_meta['epoch']
                  and created['stale'] is False and 'base_map_base64' not in created
                  and source_client.calls[calls:] == ['ceph.osdmap_preview_context', 'ceph.osd_dump',
                                                     'ceph.osd_map_export', 'ceph.osd_dump'])
            check(name + '_placement_exercised', created['summary']['changed_pgs'] == 0 if name == 'no-op'
                  else created['summary']['changed_pgs'] > 0)
            check(name + '_bound_worker_identity', created['tool_binary_sha256'] == EXPECTED_TOOL_SHA256
                  and created['worker_capabilities'] == capability and created['parser_version'] == 2
                  and created['scope']['pool_types'] == ['replicated'])
            diagnostics.stage(name + '.verify-database-row')
            with connection() as conn:
                row = conn.execute('SELECT * FROM evidence_artifacts WHERE id=%s AND cluster_id=%s AND fsid=%s',
                                   (identifier, cluster_id, fsid)).fetchone()
            check(name + '_real_database_row', row is not None and row['evidence_type'] == 'osdmap_preview')
            diagnostics.stage(name + '.verify-artifact')
            artifact = PreviewService(settings, client=source_client)._store().read_json(
                row['uri'], expected_sha256=row['sha256'], expected_size_bytes=row['size_bytes'])
            check(name + '_durable_artifact_integrity', artifact['id'] == str(identifier)
                  and artifact['fsid'] == fsid and artifact['base_sha256'] == case_request['base_sha256']
                  and artifact['base_map_base64'] == case_request['map'])
            export_path = API_ROOT + '/' + str(identifier) + '/export'
            calls = len(source_client.calls)
            first_export = request(name + '.export-first', 'POST', export_path, headers=header)
            check(name + '_export_integrity', first_export.status_code == 200
                  and first_export.headers.get('Content-Disposition', '').startswith('attachment')
                  and first_export.headers.get('X-Export-Sha256') == sha256(first_export.content)
                  and 'base_map_base64' not in first_export.json())
            check(name + '_export_adds_zero_source_calls', len(source_client.calls) == calls)
            source_client.epoch_offset = 1
            drift = request(name + '.get-epoch-drift', 'GET', API_ROOT + '/' + str(identifier))
            check(name + '_epoch_drift_detected', drift.status_code == 200 and drift.json()['stale'] is True
                  and drift.json()['current_epoch'] == case_meta['epoch'] + 1)
            calls = len(source_client.calls)
            second_export = request(name + '.export-again', 'POST', export_path, headers=header)
            check(name + '_historical_export_immutable', second_export.status_code == 200
                  and second_export.content == first_export.content
                  and second_export.headers.get('X-Export-Sha256') == sha256(second_export.content)
                  and len(source_client.calls) == calls)
            diagnostics.stage(name + '.verify-artifact-immutable')
            same_artifact = PreviewService(settings, client=source_client)._store().read_json(
                row['uri'], expected_sha256=row['sha256'], expected_size_bytes=row['size_bytes'])
            check(name + '_epoch_check_did_not_mutate_artifact', same_artifact == artifact)
            report['artifacts'].append({'case': name, 'id': str(identifier), 'artifact_sha256': row['sha256'],
                'export_sha256': sha256(first_export.content), 'base_sha256': case_request['base_sha256'],
                'base_epoch': created['base_epoch'], 'mapping_quality': created['mapping_validation']['quality']})

        diagnostics.stage('prepare-negative-capabilities')
        raw_capability = json.loads((args.spool / 'capabilities.json').read_text())
        negative_cases = (
            ('missing', None, 'OSDMAP_WORKER_UNAVAILABLE'),
            ('wrong-binary', {**raw_capability, 'tool_binary_sha256': {key: '0' * 64 for key in EXPECTED_TOOL_SHA256}},
             'OSDMAP_CAPABILITIES_INVALID'),
            ('nan-heartbeat', {**raw_capability, 'heartbeat': float('nan')}, 'OSDMAP_CAPABILITIES_INVALID'),
            ('stale-heartbeat', {**raw_capability, 'heartbeat': time.time() - 121}, 'OSDMAP_CAPABILITIES_STALE'),
        )
        for name, payload, code in negative_cases:
            negative_spool = args.spool / ('synthetic-negative-' + name + '-' + uuid4().hex)
            negative_spool.mkdir(mode=0o700)
            if payload is not None:
                (negative_spool / 'capabilities.json').write_text(json.dumps(payload))
            active_settings[0] = settings.model_copy(update={'osdmap_preview_spool': negative_spool})
            before = snapshot()
            calls = len(source_client.calls)
            negative = request('negative-capability.' + name, 'POST', API_ROOT, json=initial_body, headers=header)
            check('capability_' + name + '_fail_closed', response_error(negative, code)
                  and snapshot() == before and len(source_client.calls) == calls)
        active_settings[0] = settings

        original_read_result = PreviewService._worker_result
        original_capabilities = PreviewService.capabilities
        diagnostic = {'capability_checks': [], 'worker_envelope_received': False,
                      'worker_success_decoded': False, 'source_calls': []}
        report['tamper_diagnostic'] = diagnostic
        def trace_capabilities(service):
            value = original_capabilities(service)
            diagnostic['capability_checks'].append({'available': value.get('available'), 'code': value.get('code')})
            return value
        report['tamper_injection_executed'] = False
        def corrupt_real_result(output):
            diagnostic['worker_envelope_received'] = True
            diagnostic['worker_envelope'] = envelope_summary(output)
            result = deepcopy(original_read_result(output))
            diagnostic['worker_success_decoded'] = True
            result['tool_binary_sha256']['osdmaptool_sha256'] = '0' * 64
            report['tamper_injection_executed'] = True
            return result
        source_client.current = 'no-op'
        source_client.epoch_offset = 0
        before = snapshot()
        calls = len(source_client.calls)
        began = time.monotonic()
        try:
            with patch.object(PreviewService, '_worker_result', staticmethod(corrupt_real_result)), \
                 patch.object(PreviewService, 'capabilities', trace_capabilities):
                corrupted = request('tamper-worker-result', 'POST', API_ROOT, json=initial_body, headers=header)
        finally:
            diagnostic['duration_seconds'] = time.monotonic() - began
            diagnostic['source_calls'] = source_client.calls[calls:]
            service_trace = report.get('last_service', {})
            diagnostic['database_or_artifacts_changed'] = service_trace.get('storage_changed') if service_trace.get('http_sequence') == report.get('last_http', {}).get('sequence') else None
        report['tampered_response'] = {key: report['last_http'].get(key) for key in ('status_code', 'code')}
        check('tampered_real_worker_result_identity_rejected', report['tamper_injection_executed']
              and response_error(corrupted, 'OSDMAP_RESULT_IDENTITY_MISMATCH'))
        check('rejected_result_has_no_database_or_artifact_save', snapshot() == before)
        check('no_unauthorized_source_actions', set(source_client.calls) <= ALLOWED_ACTIONS)
        check('own_generated_jobs_removed', not any(path.is_dir() and _is_uuid(path.name)
                                                   for path in args.spool.iterdir()))
        for name, hashes in fixture_hashes.items():
            check(name + '_fixture_unchanged', sha256((args.fixtures / (name + '.json')).read_bytes()) == hashes['request_sha256']
                  and sha256((args.fixtures / (name + '.metadata.json')).read_bytes()) == hashes['metadata_sha256'])
        report['source_call_counts'] = {action: source_client.calls.count(action) for action in sorted(ALLOWED_ACTIONS)}
        report['database_artifact_rows_created'] = snapshot()[0]
    pool.close()


def _is_uuid(value):
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixtures', 'spool', 'evidence', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.fixtures, args.spool, args.evidence = (path.resolve() for path in (args.fixtures, args.spool, args.evidence))
    require(not args.report.exists(), 'REPORT_ALREADY_EXISTS')
    sources = {'test_script': Path(__file__).read_bytes(),
               'diagnostic_module': Path(__file__).with_name('integration_diagnostics.py').read_bytes()}
    report = {'kind': 'SYNTHETIC_API_REAL_WORKER_INTEGRATION', 'status': 'FAILED', 'checks': {},
              'started_at': datetime.now(timezone.utc).isoformat(),
              'test_script_sha256': sha256(sources['test_script']),
              'diagnostic_module_sha256': sha256(sources['diagnostic_module'])}
    diagnostics = IntegrationDiagnostics(report)
    try:
        run(args, report, diagnostics)
        report['status'] = 'PASS'
    except Exception as exc:
        # Do not emit raw transport/SQL/config exceptions: they may include credentials.
        diagnostics.record_failure(exc)
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        report['source_snapshots'] = write_source_snapshots(args.report.parent, sources)
        temporary = args.report.with_name('.' + args.report.name + '.' + uuid4().hex + '.tmp')
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            handle.write('\n')
        temporary.replace(args.report)
    except Exception as exc:
        print(json.dumps({'status': 'FAILED', 'report_write_error': safe_exception(exc),
                          'failure_context': report.get('failure_context'), 'last_http': report.get('last_http'),
                          'last_service': report.get('last_service')}, allow_nan=False))
        return 1
    print(json.dumps({'status': report['status'], 'checks_passed': len(report['checks']),
                      'report': str(args.report), 'failure': report.get('failure')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
