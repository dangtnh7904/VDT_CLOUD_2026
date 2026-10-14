from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time as monotonic_time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from ...platform.config import build_config_snapshot, resolve_settings
from ...services.executor_client import ExecutorClient, ExecutorClientError
from ...services.performance import fetch_prometheus_text, parse_prometheus_counters, counter_sample
from ..cluster_metrics.normalization import normalize, samples
from ..cluster_metrics.service import ACTIONS
from ..osd_info_collector.domain import validate_collection, OsdInfoError
from ..osd_info_collector.redaction import redact_collector_evidence
from .comparison import compare_collections, ComparisonError
from .repository import AsIsRepository
from .source_validation import source_valid


SLOTS = threading.BoundedSemaphore(2)
WAITING_SLOTS = threading.BoundedSemaphore(2)
COLLECTION_WAIT_SECONDS = 30
OBSERVATION_DEADLINE_SECONDS = 60
CONTROL_POLL_SECONDS = 0.1
SUPPORTED = ('mon', 'mgr', 'osd', 'rgw', 'mds')
KEY = re.compile(r'^(mon|mgr|osd|rgw|mds)\.[A-Za-z0-9_.-]{1,128}$')
METRIC_SOURCES = {
    'mon.in_quorum': 'ceph.quorum_status', 'mon.election_epoch': 'ceph.quorum_status',
    'mgr.available': 'ceph.mgr_dump', 'osd.utilization_percent': 'ceph.osd_df',
    'osd.used_kb': 'ceph.osd_df', 'osd.pg_count': 'ceph.osd_df',
}


class AsIsError(ValueError):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class CollectionControl:
    """Cooperative cancellation; a slot remains held until source calls settle."""

    def __init__(self, timeout_seconds=OBSERVATION_DEADLINE_SECONDS):
        self.cancelled = threading.Event()
        self.deadline = monotonic_time.monotonic() + timeout_seconds

    def cancel(self):
        self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise AsIsError('COLLECTION_CANCELLED', 'Đã hủy lần thu do yêu cầu không còn kết nối.', 499)
        if monotonic_time.monotonic() >= self.deadline:
            raise AsIsError('COLLECTION_TIMEOUT', 'Lần thu vượt thời gian cho phép. Kiểm tra kết nối nguồn rồi thử lại.', 504)

    def timeout(self, maximum):
        self.check()
        return min(maximum, max(0.001, self.deadline - monotonic_time.monotonic()))


@contextmanager
def collection_slot(control=None):
    if control:
        control.check()
    acquired = SLOTS.acquire(blocking=False)
    if not acquired:
        if not WAITING_SLOTS.acquire(blocking=False):
            raise AsIsError('COLLECTION_BUSY', 'Hàng chờ thu thập đã đầy. Vui lòng thử lại sau.', 429)
        try:
            wait_deadline = monotonic_time.monotonic() + COLLECTION_WAIT_SECONDS
            while not acquired:
                if control:
                    control.check()
                remaining = wait_deadline - monotonic_time.monotonic()
                if remaining <= 0:
                    break
                acquired = SLOTS.acquire(timeout=min(CONTROL_POLL_SECONDS, remaining))
        finally:
            WAITING_SLOTS.release()
        if not acquired:
            raise AsIsError('COLLECTION_BUSY', 'Nguồn dữ liệu đang bận quá lâu. Vui lòng thử lại sau.', 429)
    try:
        if control:
            control.check()
        yield
    finally:
        SLOTS.release()


def encoded(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(payload):
    return hashlib.sha256(encoded(payload)).hexdigest()


def now():
    return datetime.now(timezone.utc)


def finite_number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


class AsIsService:
    def __init__(self, settings, repository=None, client=None, fetcher=None):
        self.settings = resolve_settings(settings)
        self.repository = repository or AsIsRepository()
        self.client = client
        self.fetcher = fetcher or fetch_prometheus_text

    def identity(self):
        if not self.settings.cluster_id or not self.settings.ceph_expected_fsid:
            raise AsIsError('CLUSTER_NOT_CONFIGURED', 'Chưa cấu hình cluster ID và FSID.')
        return {'cluster_id': self.settings.cluster_id, 'fsid': self.settings.ceph_expected_fsid}

    def _validate_scope(self, daemon_types, daemon_keys):
        if not daemon_types or set(daemon_types) - set(SUPPORTED) or len(set(daemon_types)) != len(daemon_types):
            raise AsIsError('INVALID_DAEMON_TYPE', 'Chọn loại MON, MGR, OSD, RGW hoặc MDS; không chọn trùng.', 422)
        if len(daemon_keys) > 128 or len(set(daemon_keys)) != len(daemon_keys):
            raise AsIsError('INVALID_DAEMON_SCOPE', 'Chọn tối đa 128 daemon khác nhau.', 422)
        allowed = {value.removeprefix('osd.') for value in self.settings.upgrade_allowed_osd_set}
        for key in daemon_keys:
            if not KEY.fullmatch(key) or key.split('.', 1)[0] not in daemon_types:
                raise AsIsError('INVALID_DAEMON_SCOPE', 'Danh tính daemon không hợp lệ hoặc không đúng loại.', 422)
            if key.startswith('osd.') and key[4:] not in allowed:
                raise AsIsError('DAEMON_SCOPE_REJECTED', 'OSD nằm ngoài phạm vi được cấu hình.', 403)

    def _scrape(self, control):
        token = self.settings.performance_prometheus_bearer_token
        text = self.fetcher(self.settings.performance_prometheus_url, timeout_seconds=control.timeout(10),
                            bearer_token=token.get_secret_value() if token else None)
        control.check()
        labels = set(re.findall(r'\b(?:fsid|cluster_fsid)="([^"\n]+)"', text))
        if labels and labels != {self.settings.ceph_expected_fsid}:
            raise AsIsError('FSID_MISMATCH', 'Nguồn chỉ số thuộc cluster FSID khác.')
        counters, metric_names = parse_prometheus_counters(text)
        return {'at': now(), 'counters': counters, 'metric_names': metric_names}

    def observe(self, *, daemon_types=None, daemon_keys=None, deep=False, control=None):
        identity = self.identity()
        daemon_keys = daemon_keys or []
        daemon_types = daemon_types or sorted({key.split('.', 1)[0] for key in daemon_keys}) or list(SUPPORTED)
        self._validate_scope(daemon_types, daemon_keys)
        # Saved deep collections retain their configured bounded collector budget.
        # HTTP observations/exports supply a shorter disconnect-aware control.
        control = control or CollectionControl(OBSERVATION_DEADLINE_SECONDS +
            (self.settings.osd_info_collector_timeout_seconds if deep else 0))
        with collection_slot(control):
            try:
                return self._observe(identity, daemon_types, daemon_keys, deep, control)
            except ExecutorClientError as exc:
                control.check()
                raise AsIsError(exc.code, 'Không đọc được cluster. Kiểm tra kết nối SSH và quyền đọc.', 503) from None

    def _observe(self, identity, daemon_types, daemon_keys, deep, control):
        client = self.client or ExecutorClient.from_settings()
        started = now()
        control.check()
        capabilities = (client.request('capabilities', timeout_seconds=control.timeout(15))
            if isinstance(client, ExecutorClient) else client.capabilities())
        control.check()
        if capabilities.get('fsid') != identity['fsid']:
            raise AsIsError('FSID_MISMATCH', 'Executor đang nối tới cluster FSID khác.')
        available = set(capabilities.get('actions') or [])
        sources, evidence, limitations = {}, {}, []
        first = None
        prometheus = self.settings.performance_source == 'prometheus' and bool(self.settings.performance_prometheus_url)
        if prometheus:
            try:
                first = self._scrape(control)
            except AsIsError:
                raise
            except Exception:
                sources['prometheus'] = {'quality': 'UNAVAILABLE', 'reason': 'TELEMETRY_READ_FAILED'}
        actions = list(dict.fromkeys(action for scope in ['cluster', 'host', 'pool', 'osd', 'mon', 'mgr', *daemon_types] for action in ACTIONS[scope]))
        actions += ['ceph.osd_dump', 'ceph.daemon_ls']
        if deep:
            actions += ['ceph.crush_dump', 'ceph.pg_dump', 'ceph.client_environment']
        actions = list(dict.fromkeys(actions))
        def read(action):
            control.check()
            begin = now().isoformat()
            if action not in available:
                return action, {'quality': 'UNSUPPORTED', 'reason': 'EXECUTOR_ACTION_UNSUPPORTED', 'started_at': begin}
            try:
                maximum = 20 if action == 'ceph.client_environment' else min(self.settings.rbd_executor_timeout_seconds, 15)
                response = client.request(action, timeout_seconds=control.timeout(maximum))
                control.check()
                if response.get('fsid') != identity['fsid']:
                    raise AsIsError('FSID_MISMATCH', 'FSID thay đổi trong lúc thu thập.')
                quality = 'VALID'
                if not source_valid(action, response.get('data')):
                    reason = 'INVALID_DAEMON_SOURCE_SCHEMA' if action in {'ceph.daemon_ls', 'ceph.fs_dump'} else 'INVALID_SOURCE_SCHEMA'
                    return action, {'quality': 'UNAVAILABLE', 'reason': reason, 'started_at': begin, 'completed_at': now().isoformat()}
                if action == 'ceph.client_environment':
                    environment = response.get('data')
                    if not isinstance(environment, dict) or environment.get('kind') != 'CEPH_CLIENT_ENVIRONMENT' or environment.get('scope') != 'SSH_CLIENT_HOST_ONLY':
                        return action, {'quality': 'UNAVAILABLE', 'reason': 'INVALID_ENVIRONMENT_EVIDENCE', 'started_at': begin}
                    quality = environment.get('quality') if environment.get('quality') in {'VALID', 'PARTIAL'} else 'PARTIAL'
                reason, observed_at = None, response.get('collected_at')
                try:
                    source_at = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
                    if source_at.tzinfo is None or (source_at - now()).total_seconds() > 5:
                        raise ValueError('invalid source time')
                    observed_at = source_at.astimezone(timezone.utc).isoformat()
                    if (datetime.fromisoformat(begin) - source_at).total_seconds() > 5:
                        quality, reason = 'STALE', 'SOURCE_PREDATES_REQUEST'
                except (AttributeError, TypeError, ValueError):
                    quality, reason, observed_at = 'UNAVAILABLE', 'INVALID_SOURCE_TIMESTAMP', None
                return action, {'quality': quality, 'reason': reason, 'started_at': begin, 'completed_at': now().isoformat(),
                                'observed_at': observed_at, 'data': response.get('data')}
            except ExecutorClientError as exc:
                if exc.code == 'FSID_MISMATCH':
                    raise AsIsError('FSID_MISMATCH', 'FSID thay đổi trong lúc thu thập.') from None
                return action, {'quality': 'UNAVAILABLE', 'reason': exc.code, 'started_at': begin,
                                'completed_at': now().isoformat()}
        worker = ThreadPoolExecutor(max_workers=3)
        pending = {worker.submit(read, action) for action in actions}
        try:
            while pending:
                control.check()
                completed, pending = wait(pending, timeout=CONTROL_POLL_SECONDS, return_when=FIRST_COMPLETED)
                for future in completed:
                    action, result = future.result()
                    evidence[action] = result
                    sources[action] = {key: value for key, value in result.items() if key != 'data'}
        finally:
            # Never free the collection slot while its admitted SSH reads remain
            # in flight. Cancel only queued reads; wait for bounded running calls.
            for future in pending:
                future.cancel()
            worker.shutdown(wait=True, cancel_futures=True)
        control.check()
        all_rows = [row for kind in daemon_types for row in normalize(kind, evidence)]
        allowed = {value.removeprefix('osd.') for value in self.settings.upgrade_allowed_osd_set}
        all_rows = [row for row in all_rows if row['scope_type'] != 'osd' or row['id'] in allowed]
        if daemon_keys:
            all_rows = [row for row in all_rows if f"{row['scope_type']}.{row['id']}" in daemon_keys]
        if len(all_rows) > 128:
            raise AsIsError('SCOPE_TOO_LARGE', 'Phạm vi có hơn 128 daemon. Hãy chọn loại hoặc daemon cụ thể.', 422)
        deep_rows = {}
        deep_context = None
        if deep and 'osd' in daemon_types:
            ids = tuple(sorted(int(row['id']) for row in all_rows if row['scope_type'] == 'osd'))
            if ids and 'ceph.osd_info_collect' in available:
                try:
                    control.check()
                    if isinstance(client, ExecutorClient):
                        response = client.request('ceph.osd_info_collect', {'osd_ids': list(ids)},
                            timeout_seconds=control.timeout(self.settings.osd_info_collector_timeout_seconds),
                            max_response_bytes=self.settings.osd_info_collector_max_output_bytes)
                        raw = client._rbd_data(response, 'ceph.osd_info_collect')
                    else:
                        raw = client.ceph_osd_info_collect(list(ids))
                    control.check()
                    validated = validate_collection(raw, expected_fsid=identity['fsid'], requested_osd_ids=ids)
                    deep_rows = {str(row['osd_id']): redact_collector_evidence(row) for row in validated.records}
                    deep_context = redact_collector_evidence({'cluster_summary': validated.cluster_summary,
                        'cluster_evidence': raw.get('cluster_evidence'), 'errors': raw.get('errors'),
                        'collector_version': validated.collector_version})
                    sources['ceph.osd_info_collect'] = {'quality': validated.quality.value,
                        'observed_at': validated.collected_at.isoformat(), 'collector_version': validated.collector_version}
                except (ExecutorClientError, OsdInfoError) as exc:
                    if exc.code == 'FSID_MISMATCH':
                        raise AsIsError(exc.code, 'Nguồn OSD thuộc cluster FSID khác.') from None
                    sources['ceph.osd_info_collect'] = {'quality': 'UNAVAILABLE', 'reason': exc.code}
            elif ids:
                sources['ceph.osd_info_collect'] = {'quality': 'UNSUPPORTED', 'reason': 'EXECUTOR_ACTION_UNSUPPORTED'}
        system = normalize('cluster', evidence)[0]
        system['hosts'] = [r for r in normalize('host', evidence) if r['id'] in self.settings.upgrade_allowed_host_set]
        system['pools'] = [r for r in normalize('pool', evidence) if r['name'] in self.settings.upgrade_allowed_pool_set]
        system['metrics'] = []
        osd_dump = evidence.get('ceph.osd_dump', {}).get('data') or {}
        system['osdmap_epoch'] = osd_dump.get('epoch')
        system['flags'] = osd_dump.get('flags')
        system['osd_count'] = len(osd_dump['osds']) if isinstance(osd_dump.get('osds'), list) else None
        system['mon'] = normalize('mon', evidence)
        system['mgr'] = normalize('mgr', evidence)
        if 'mds' in daemon_types:
            system['cephfs'] = evidence.get('ceph.fs_dump', {}).get('data')
        if deep:
            system['environment'] = evidence.get('ceph.client_environment', {}).get('data')
            system['crush_map'] = evidence.get('ceph.crush_dump', {}).get('data')
            system['pg_map'] = evidence.get('ceph.pg_dump', {}).get('data')
            system['placement_overrides'] = {k: osd_dump.get(k) for k in ('pg_temp', 'primary_temp', 'pg_upmap', 'pg_upmap_items')}
            system['coverage'] = {
                'A0.1': 'Môi trường SSH client host: OS/kernel, Python, shell được khai báo, tool/client versions và thời điểm. Đọc chất lượng từng trường; không đại diện máy khác hoặc daemon container.',
                'A0.2': 'Health, quorum MON, MGR, dung lượng, flags từ các nguồn có trạng thái riêng.',
                'A0.3': 'Dữ liệu OSD chuyên sâu của các OSD được yêu cầu; thiếu trường được ghi rõ.',
                'A0.4': 'CRUSH JSON gồm rules/choose_args khi nguồn cung cấp; chưa xuất CRUSH binary riêng.',
                'A0.5': 'PG dump pgs_brief toàn cụm và override từ OSDMap; bộ PG nguồn có thời điểm riêng.',
                'A0.6': 'Pool config/capacity; chưa thu RBD mapping/image trong chế độ chỉ đọc này.',
                'A0.7': 'Daemon version/image/incarnation từ orchestrator; chưa thu service specs và upgrade status.',
                'A0.8': 'Một phần: health, PG recovery/scrub và capacity; chưa có clock sync/crash/helper đầy đủ.'}
        if deep_context is not None:
            system['osd_collection_context'] = deep_context
        orchestrated = {row.get('daemon_name'): row for row in (evidence.get('ceph.daemon_ls', {}).get('data') or []) if isinstance(row, dict)}
        performance = {}
        if first:
            try:
                second = self._scrape(control)
                window = (second['at'] - first['at']).total_seconds()
                if window <= 0:
                    raise ValueError('non-monotonic measurement')
                for osd_id, counters in second['counters'].items():
                    if osd_id not in allowed:
                        continue
                    measured = counter_sample(fsid=identity['fsid'], scope_type='osd', scope_id=osd_id,
                        captured_at=second['at'], counters=counters, previous_counters=first['counters'].get(osd_id),
                        previous_captured_at=first['at'], metric_names=second['metric_names'])
                    performance[osd_id] = [{'metric_id': f'osd.{field}', 'value': getattr(measured, field),
                        'unit': 'ops/s' if 'iops' in field else 'bytes/s', 'kind': 'rate',
                        'observed_at': second['at'].isoformat(), 'window_seconds': window,
                        'quality': 'UNAVAILABLE' if measured.partial else 'VALID',
                        'reason': ','.join(measured.metadata['reasons']) or None}
                        for field in ('read_iops', 'write_iops', 'total_iops', 'read_bytes_per_second', 'write_bytes_per_second', 'total_bytes_per_second')]
                    for metric in performance[osd_id]:
                        value = metric['value']
                        if value is not None and (not math.isfinite(value) or value < 0):
                            metric.update(value=None, quality='UNAVAILABLE', reason='NUMERIC_OUT_OF_RANGE')
                sources['prometheus'] = {'quality': 'PARTIAL' if any(m['quality'] != 'VALID' for entries in performance.values() for m in entries) or not performance else 'VALID', 'started_at': first['at'].isoformat(),
                    'completed_at': second['at'].isoformat(), 'window_seconds': window,
                    'identity_binding': 'configured_endpoint_and_verified_ceph_fsid'}
                # A cluster total is valid only with the identical complete OSD population in both samples.
                present = {r['id'] for r in normalize('osd', evidence)}
                complete = present and present == set(first['counters']) == set(second['counters']) and present <= allowed
                if complete and performance and all(m['quality'] == 'VALID' for entries in performance.values() for m in entries):
                    system['metrics'] = [{**performance[next(iter(performance))][i],
                        'metric_id': performance[next(iter(performance))][i]['metric_id'].replace('osd.', 'cluster.', 1),
                        'value': sum(entries[i]['value'] for entries in performance.values())} for i in range(6)]
                    for metric in system['metrics']:
                        if not math.isfinite(metric['value']):
                            metric.update(value=None, quality='UNAVAILABLE', reason='NUMERIC_OUT_OF_RANGE')
                            sources['prometheus']['quality'] = 'PARTIAL'
                else:
                    limitations.append('Chưa đủ quần thể OSD đồng nhất để tính tổng I/O toàn cluster.')
            except AsIsError:
                raise
            except Exception:
                sources['prometheus'] = {'quality': 'UNAVAILABLE', 'reason': 'TELEMETRY_READ_FAILED'}
        elif not prometheus:
            limitations.append('Chưa cấu hình nguồn Prometheus cho IOPS và thông lượng.')
        control.check()
        final_identity = (client.request('ceph.fsid', timeout_seconds=control.timeout(15))
            if isinstance(client, ExecutorClient) else client.ceph_fsid())
        control.check()
        if final_identity.get('fsid') != identity['fsid']:
            raise AsIsError('FSID_MISMATCH', 'FSID thay đổi trong lúc thu thập.')
        daemons = []
        for row in all_rows:
            kind, daemon_id = row['scope_type'], row['id']
            source_times = [sources[a].get('observed_at') for a in ACTIONS[kind] if sources[a].get('observed_at')]
            observed_at = max(source_times) if source_times else None
            fields = {k: v for k, v in row.items() if k not in {'id', 'name', 'scope_type'}}
            runtime = orchestrated.get(f'{kind}.{daemon_id}', {})
            if row.get('identity_source') == 'ceph.daemon_ls':
                # A fresh request to orch ps is not a fresh daemon-cache sample.
                observed_at = runtime.get('last_refresh')
            elif row.get('identity_source') == 'ceph.fs_dump':
                observed_at = sources['ceph.fs_dump'].get('observed_at')
            fields.update({'hostname': runtime.get('hostname'), 'ceph_version': runtime.get('version'),
                'container_image': runtime.get('container_image_name'), 'container_image_id': runtime.get('container_image_id'),
                'container_image_digests': runtime.get('container_image_digests'), 'container_id': runtime.get('container_id'),
                'started_at': runtime.get('started'), 'orchestrator_observed_at': runtime.get('last_refresh')})
            if runtime.get('status_desc') is not None:
                fields['daemon_status'] = runtime['status_desc']
            if kind == 'mon':
                fields['status'] = 'Trong quorum' if fields.get('in_quorum') is True else 'Ngoài quorum' if fields.get('in_quorum') is False else runtime.get('status_desc')
            if kind == 'osd':
                state = next((r for r in osd_dump.get('osds', []) if str(r.get('osd')) == daemon_id), {})
                fields.update({k: state.get(k) for k in ('up', 'in', 'primary_affinity')})
            missing = [a for a in ACTIONS[kind] if sources[a]['quality'] != 'VALID']
            if kind in {'rgw', 'mds'}:
                missing.append('Chưa có nguồn chỉ số request/session và percentile độ trễ cho loại daemon này.')
            if not runtime:
                missing.append('DAEMON_RUNTIME_UNAVAILABLE')
            if kind == 'osd' and deep:
                if daemon_id in deep_rows:
                    fields.update(deep_rows[daemon_id])
                    observed_at = sources['ceph.osd_info_collect'].get('observed_at') or observed_at
                    if deep_rows[daemon_id]['quality'] != 'VALID':
                        missing.extend(deep_rows[daemon_id].get('warnings') or ['DEEP_OSD_PARTIAL'])
                else:
                    missing.append('DEEP_OSD_UNAVAILABLE')
            metric_rows = samples({'observed_at': observed_at, 'resources': [row]})
            for metric in metric_rows:
                source = sources[METRIC_SOURCES[metric['metric_id']]]
                metric['observed_at'] = source.get('observed_at')
                metric['kind'] = 'gauge'
                value = metric['value']
                boolean = metric['unit'] == 'boolean'
                valid_value = isinstance(value, bool) if boolean else finite_number(value) and value >= 0
                if value is not None and not valid_value:
                    metric.update(value=None, quality='UNAVAILABLE', reason='INVALID_SOURCE_FIELD')
                elif source['quality'] != 'VALID':
                    metric.update(quality=source['quality'], reason=source.get('reason') or 'SOURCE_QUALITY_INSUFFICIENT')
            try:
                refresh = runtime.get('last_refresh')
                if not isinstance(refresh, str) or not refresh.strip():
                    raise ValueError('Invalid orchestrator timestamp')
                source_at = datetime.fromisoformat(refresh.replace('Z', '+00:00'))
                signed_age = (now() - source_at).total_seconds()
                source_age = max(0, signed_age) if signed_age >= -5 else None
                source_quality = 'UNAVAILABLE' if source_age is None else 'VALID' if source_age <= self.settings.telemetry_max_age_seconds else 'STALE'
                for name, unit, raw_value in [('container.memory_usage', 'bytes', runtime.get('memory_usage')),
                    ('container.cpu_percentage', 'percent', str(runtime.get('cpu_percentage', '')).rstrip('%'))]:
                    try:
                        value = float(raw_value)
                    except (TypeError, ValueError):
                        value = None
                    if value is not None and (not math.isfinite(value) or value < 0):
                        value = None
                    metric_rows.append({'metric_id': name, 'value': value if value is not None and math.isfinite(value) else None,
                        'unit': unit, 'kind': 'gauge', 'source': 'ceph_orchestrator_refreshed_container_stats',
                        'observed_at': runtime['last_refresh'], 'age_seconds': source_age,
                        'quality': source_quality if value is not None else 'UNAVAILABLE',
                        'reason': 'INVALID_SOURCE_TIMESTAMP' if source_age is None else 'SOURCE_FIELD_MISSING' if value is None else 'SAMPLE_WINDOW_UNAVAILABLE' if name.endswith('cpu_percentage') else None})
            except (KeyError, ValueError, TypeError):
                missing.append('DAEMON_RUNTIME_TIMESTAMP_UNAVAILABLE')
            if kind == 'osd':
                metric_rows += performance.get(daemon_id, [])
            missing.extend(f"{m['metric_id']}:{m['quality']}" for m in metric_rows if m.get('quality') not in {'VALID', None})
            daemons.append({'key': f'{kind}.{daemon_id}', 'type': kind, 'id': daemon_id, 'name': row['name'],
                'observed_at': observed_at, 'quality': 'PARTIAL' if missing else 'VALID',
                'fields': fields, 'metrics': metric_rows, 'limitations': missing})
        found = {row['key'] for row in daemons}
        missing = sorted(set(daemon_keys) - found)
        if not daemons and daemon_keys:
            limitations.append('Không đọc được daemon đã chọn; xem lỗi từng nguồn.')
        limitations.append('CPU/RAM container lấy từ orchestrator khi có, kèm thời điểm nguồn; chưa có host/process telemetry đầy đủ hoặc percentile độ trễ.')
        completed = now()
        quality = 'PARTIAL' if missing or any(s['quality'] != 'VALID' for s in sources.values()) or any(r['quality'] != 'VALID' for r in daemons) else 'VALID'
        result = {'schema_version': 1, 'collector_version': 'as-is-1.2', 'id': str(uuid4()), 'kind': 'LIVE_OBSERVATION',
            **identity, 'started_at': started.isoformat(), 'completed_at': completed.isoformat(),
            'observed_at': started.isoformat(), 'window_seconds': (completed - started).total_seconds(),
            'quality': quality, 'requested_daemon_types': daemon_types, 'requested_daemon_keys': daemon_keys,
            'missing_daemon_keys': missing, 'daemons': sorted(daemons, key=lambda r: (r['type'], r['id'])),
            'system': system, 'sources': sources, 'limitations': limitations,
            'capabilities': {kind: True for kind in SUPPORTED},
            'freshness': {'mode': 'READ_ON_REQUEST', 'source_started_at': started.isoformat(), 'source_completed_at': completed.isoformat()}}
        result = redact_collector_evidence(result)
        control.check()
        if len(encoded(result)) > min(self.settings.evidence_max_artifact_bytes, 16 * 1024 * 1024):
            raise AsIsError('COLLECTION_TOO_LARGE', 'Dữ liệu vượt giới hạn; hãy thu một nhóm daemon nhỏ hơn.', 413)
        return result

    def create(self, *, daemon_keys, phase, note='', idempotency_key=None, actor='local-operator'):
        if not daemon_keys or phase not in {'BEFORE', 'DURING', 'AFTER'}:
            raise AsIsError('INVALID_COLLECTION', 'Chọn daemon và một trong ba giai đoạn thu thập.', 422)
        identity = self.identity()
        request_hash = digest({'keys': sorted(daemon_keys), 'phase': phase, 'note': note})
        collection_id = uuid5(NAMESPACE_URL, f"as-is:{identity['cluster_id']}:{identity['fsid']}:{idempotency_key}") if idempotency_key else uuid4()
        previous = self.repository.get(collection_id, **identity, include_deleted=True)
        if previous:
            if previous['request_hash'] != request_hash:
                raise AsIsError('IDEMPOTENCY_CONFLICT', 'Mã yêu cầu này đã dùng cho phạm vi khác.')
            if previous.get('deleted_at'):
                raise AsIsError('COLLECTION_DELETED', 'Collection đã bị xóa; hãy khôi phục hoặc tạo yêu cầu mới.')
            return self.get(collection_id)
        payload = self.observe(daemon_keys=daemon_keys, deep=True)
        snapshot = build_config_snapshot(self.settings)
        payload.update({'id': str(collection_id), 'kind': 'AS_IS_COLLECTION', 'phase': phase, 'note': note,
                        'actor': actor, 'config_hash': snapshot.config_hash,
                        'config': redact_collector_evidence(snapshot.payload)})
        self.repository.save(payload, sha256=digest(payload), request_hash=request_hash, actor=actor)
        winner = self.repository.get(collection_id, **identity)
        if not winner or winner['request_hash'] != request_hash:
            raise AsIsError('IDEMPOTENCY_CONFLICT', 'Yêu cầu đồng thời đã dùng mã này cho phạm vi khác.')
        return self.get(collection_id)

    def _get_verified(self, collection_id, *, include_deleted=False):
        row = self.repository.get(collection_id, **self.identity(), include_deleted=include_deleted)
        if row is None:
            raise AsIsError('COLLECTION_NOT_FOUND', 'Không tìm thấy collection trong cluster này.', 404)
        payload = row['payload']
        try:
            valid = isinstance(payload, dict) and digest(payload) == row['sha256'] and all(payload.get(k) == v for k, v in self.identity().items()) and payload.get('id') == str(collection_id)
        except (ValueError, TypeError, RecursionError):
            valid = False
        if not valid:
            raise AsIsError('COLLECTION_INTEGRITY_FAILED', 'Collection không khớp mã kiểm tra toàn vẹn.')
        return {**payload, 'sha256': row['sha256'], 'deleted_at': row.get('deleted_at'),
                'artifact': {'verified': True, 'sha256': row['sha256']}, 'historical': True}

    def get(self, collection_id, *, include_deleted=False):
        payload = self._get_verified(collection_id, include_deleted=include_deleted)
        allowed_osds = {value.removeprefix('osd.') for value in self.settings.upgrade_allowed_osd_set}
        keys = set(payload.get('requested_daemon_keys') or []) | {row['key'] for row in payload.get('daemons', [])}
        system = payload.get('system') or {}
        if (any(key.startswith('osd.') and key[4:] not in allowed_osds for key in keys)
            or any(row.get('id') not in self.settings.upgrade_allowed_host_set for row in system.get('hosts', []))
            or any(row.get('name') not in self.settings.upgrade_allowed_pool_set for row in system.get('pools', []))):
            raise AsIsError('COLLECTION_SCOPE_REJECTED', 'Collection đã lưu chứa OSD/host/pool ngoài phạm vi hiện tại. Không thể xem, xuất hoặc so sánh; dữ liệu gốc vẫn được giữ nguyên.', 403)
        return payload

    def export_view(self, collection_id, *, include_deleted=False, daemon_type=None, daemon_key=None):
        original = self.get(collection_id, include_deleted=include_deleted)
        if daemon_type is None and daemon_key is None:
            return original
        if daemon_type is not None and daemon_type not in SUPPORTED:
            raise AsIsError('INVALID_DAEMON_TYPE', 'Loại daemon không được hỗ trợ.', 422)
        if daemon_key is not None:
            if not KEY.fullmatch(daemon_key):
                raise AsIsError('INVALID_DAEMON_SCOPE', 'Danh tính daemon không hợp lệ.', 422)
            key_type = daemon_key.split('.', 1)[0]
            if daemon_type is not None and daemon_type != key_type:
                raise AsIsError('INVALID_DAEMON_SCOPE', 'Daemon đã chọn không đúng loại được lọc.', 422)
            daemon_type = daemon_type or key_type
        daemons = [row for row in original.get('daemons', [])
            if row.get('type') == daemon_type and (daemon_key is None or row.get('key') == daemon_key)]
        if not daemons:
            raise AsIsError('DAEMON_NOT_IN_COLLECTION', 'Bộ As-is này không chứa daemon phù hợp với bộ lọc.', 404)
        # This is a projection, not the signed original collection. Its byte
        # checksum is emitted by _export; the parent hash is labelled separately.
        projected = {key: original.get(key) for key in ('schema_version', 'collector_version', 'id',
            'cluster_id', 'fsid', 'started_at', 'completed_at', 'observed_at', 'window_seconds',
            'phase', 'note', 'actor', 'quality', 'deleted_at', 'historical')}
        projected.update({'kind': 'FILTERED_AS_IS_EXPORT', 'daemons': daemons,
            'source_collection': {'id': original['id'], 'sha256': original['sha256'], 'verified': True},
            'source_sha256': original['sha256'], 'filter': {'daemon_type': daemon_type, 'daemon_key': daemon_key},
            'requested_daemon_types': [daemon_type], 'requested_daemon_keys': [row['key'] for row in daemons]})
        return projected

    def list(self, *, daemon_type=None, from_date=None, to_date=None, phase=None, include_deleted=False,
             limit=10, cursor=None, query=None, quality=None, daemon_key=None):
        from .pagination import decode_cursor, encode_cursor, InvalidCursor

        def boundary(value):
            if value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError('invalid date format')
            return datetime.combine(date.fromisoformat(value), time.min, timezone(timedelta(hours=7))) if value else None
        try:
            start, end = boundary(from_date), boundary(to_date)
            exclusive_end = end + timedelta(days=1) if end else None
        except (ValueError, OverflowError):
            raise AsIsError('INVALID_DATE', 'Ngày lọc phải có dạng YYYY-MM-DD.', 422) from None
        if start and end and start > end:
            raise AsIsError('INVALID_DATE_RANGE', 'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.', 422)
        if not isinstance(limit, int) or not 1 <= limit <= 200:
            raise AsIsError('INVALID_PAGE_SIZE', 'Mỗi trang nhận từ 1 đến 200 bộ As-is.', 422)
        filters = {**self.identity(), 'daemon_type': daemon_type, 'start': start,
            'end': exclusive_end, 'phase': phase,
            'include_deleted': include_deleted, 'query': query.strip() if query and query.strip() else None,
            'quality': quality, 'daemon_key': daemon_key}
        try:
            before = decode_cursor(cursor, filters)
        except InvalidCursor as exc:
            raise AsIsError('INVALID_CURSOR', str(exc), 422) from None
        rows = self.repository.list(**filters, before=before, limit=limit + 1)
        has_more = len(rows) > limit
        items = rows[:limit]
        return {'items': items, 'next_cursor': encode_cursor(items[-1], filters) if has_more else None,
            'has_more': has_more, 'timezone': 'Asia/Saigon', 'limit': limit}

    def set_deleted(self, collection_id, *, deleted, actor):
        self._get_verified(collection_id, include_deleted=True)
        row = self.repository.set_deleted(collection_id, **self.identity(), deleted=deleted, actor=actor)
        if not row:
            raise AsIsError('COLLECTION_NOT_FOUND', 'Không tìm thấy collection.', 404)
        return {'id': str(collection_id), 'deleted_at': row.get('deleted_at'), 'sha256': row['sha256'],
                'status': 'DELETED' if deleted else 'RESTORED'}

    def compare(self, *, collection_a_id, collection_b_id, daemon_type, daemon_keys=None):
        try:
            return compare_collections(self.get(collection_a_id), self.get(collection_b_id), daemon_type, daemon_keys)
        except ComparisonError as exc:
            raise AsIsError('COMPARISON_SCOPE_MISMATCH', str(exc), 422) from exc
