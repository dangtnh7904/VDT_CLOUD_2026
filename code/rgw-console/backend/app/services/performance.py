from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from typing import Any, Iterable
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from ..config import get_settings
from ..db import connection


PROMETHEUS_LINE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>.*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|NaN|[-+]?Inf)"
    r"(?:\s+\d+)?$"
)
PROMETHEUS_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"(?:,|$)')

COUNTER_ALIASES: dict[str, tuple[str, ...]] = {
    "read_ops": ("ceph_osd_op_r",),
    "write_ops": ("ceph_osd_op_w",),
    "read_bytes": ("ceph_osd_op_r_out_bytes", "ceph_osd_op_out_bytes"),
    "write_bytes": ("ceph_osd_op_w_in_bytes", "ceph_osd_op_in_bytes"),
}

READ_OPERATION_KINDS = ("GET", "HEAD", "LIST", "RBD_FILE_READ")
WRITE_OPERATION_KINDS = (
    "PUT",
    "UPDATE",
    "DELETE",
    "RBD_CREATE",
    "RBD_FILE_WRITE",
    "RBD_FILE_DELETE",
    "RBD_DELETE",
)
SUPPORTED_SCOPES = {
    "application": frozenset({"cluster"}),
    "ceph": frozenset({"cluster", "osd"}),
    "device": frozenset(),
}


class PerformanceTelemetryError(RuntimeError):
    """A performance source could not produce trustworthy telemetry."""

    def __init__(self, code: str, message: str | None = None, *, http_status: int | None = None):
        # Only stable codes and authored messages reach exports/logs. HTTP error
        # bodies, configured URLs and exception strings can contain secrets.
        super().__init__(message or code)
        self.code = code
        self.http_status = http_status

    def diagnostics(self) -> dict[str, Any]:
        result: dict[str, Any] = {"quality": "UNAVAILABLE", "reason": self.code}
        if self.http_status is not None:
            result["http_status"] = self.http_status
        return result


class PrometheusText(str):
    """Text-compatible scrape result retaining non-sensitive HTTP evidence."""

    def __new__(cls, value: str, *, http_status: int | None = None):
        result = super().__new__(cls, value)
        result.http_status = http_status
        return result


MAX_PROMETHEUS_BYTES = 16 * 1024 * 1024


class _NoMetricsRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        # The operator and the verified MGR service name one endpoint. Following
        # a redirect changes that identity and can forward its bearer token.
        try:
            fp.close()
        finally:
            raise PerformanceTelemetryError("METRICS_REDIRECT_REJECTED", http_status=code) from None


def _open_prometheus_request(request: Request, timeout: float):
    return build_opener(_NoMetricsRedirects()).open(request, timeout=timeout)


@dataclass
class PerformanceSample:
    fsid: str
    source: str
    scope_type: str
    scope_id: str
    captured_at: datetime
    window_seconds: float
    read_iops: float | None = None
    write_iops: float | None = None
    total_iops: float | None = None
    read_bytes_per_second: float | None = None
    write_bytes_per_second: float | None = None
    total_bytes_per_second: float | None = None
    read_latency_ms: float | None = None
    write_latency_ms: float | None = None
    average_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    success_count: int | None = None
    error_count: int | None = None
    fresh: bool = True
    reset_detected: bool = False
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _unescape_prometheus_label(value: str) -> str:
    return value.replace(r"\n", "\n").replace(r'\"', '"').replace(r"\\", "\\")


def _parse_labels(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    labels: dict[str, str] = {}
    position = 0
    while position < len(raw):
        match = PROMETHEUS_LABEL_RE.match(raw, position)
        if not match:
            raise PerformanceTelemetryError("METRICS_PARSE_FAILED", "invalid Prometheus label set")
        if match.group(1) in labels:
            raise PerformanceTelemetryError("METRICS_PARSE_FAILED", "duplicate Prometheus label name")
        labels[match.group(1)] = _unescape_prometheus_label(match.group(2))
        position = match.end()
    return labels


def parse_prometheus_counters(text: str) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """Extract the minimum Pacific OSD client-I/O counters.

    The return value is keyed by OSD id (without the ``osd.`` prefix). Duplicate
    series are rejected so an exporter/relabeling error cannot silently double
    cluster totals.
    """

    parsed: dict[str, list[tuple[dict[str, str], float]]] = {}
    relevant_names = {name for aliases in COUNTER_ALIASES.values() for name in aliases}
    had_data_line = False
    if not isinstance(text, str) or not text.strip():
        raise PerformanceTelemetryError("METRICS_RESPONSE_EMPTY")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        had_data_line = True
        match = PROMETHEUS_LINE_RE.fullmatch(line)
        if not match:
            if any(line.startswith(name + suffix) for name in relevant_names for suffix in ("{", " ")):
                raise PerformanceTelemetryError("METRICS_PARSE_FAILED")
            continue
        value = float(match.group("value"))
        if not math.isfinite(value):
            continue
        parsed.setdefault(match.group("name"), []).append(
            (_parse_labels(match.group("labels")), value)
        )

    selected_names: dict[str, str] = {}
    for semantic, aliases in COUNTER_ALIASES.items():
        for name in aliases:
            if name in parsed:
                selected_names[semantic] = name
                break

    counters: dict[str, dict[str, float]] = {}
    duplicates: set[tuple[str, str]] = set()
    for semantic, metric_name in selected_names.items():
        for labels, value in parsed[metric_name]:
            daemon = labels.get("ceph_daemon", "")
            if not daemon.startswith("osd."):
                continue
            osd_id = daemon.removeprefix("osd.")
            if not osd_id.isascii() or not osd_id.isdigit() or value < 0:
                raise PerformanceTelemetryError("METRICS_INVALID_COUNTER")
            key = (osd_id, semantic)
            if semantic in counters.setdefault(osd_id, {}):
                duplicates.add(key)
                continue
            counters[osd_id][semantic] = value

    if duplicates:
        raise PerformanceTelemetryError("METRICS_DUPLICATE_SERIES", "duplicate Prometheus counter series")
    if not counters:
        code = "METRICS_PARSE_FAILED" if had_data_line and not parsed else "METRICS_OSD_COUNTERS_MISSING"
        raise PerformanceTelemetryError(code)
    return counters, selected_names


def _metrics_endpoint(url: str | None) -> tuple[str, str, int, str] | None:
    """Canonicalize only the MGR's root and documented /metrics route."""
    try:
        parts = urlsplit(url or "")
        path = parts.path.rstrip("/")
        if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or path not in {"", "/metrics"}):
            return None
        port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
        if not 1 <= port <= 65535:
            return None
        return (parts.scheme, parts.hostname.lower(), port, "/metrics")
    except (TypeError, ValueError):
        return None


def prometheus_identity_binding(
    text: str,
    expected_fsid: str,
    *,
    configured_url: str | None = None,
    verified_service_url: str | None = None,
) -> str:
    """Bind used counter series, or a live FSID-verified MGR service endpoint.

    Callers must only pass verified_service_url from a fresh CLI response whose
    enclosing FSID was checked. Merely configuring CEPH_EXPECTED_FSID does not
    prove the origin of an unrelated HTTP scrape.
    """
    relevant_names = {name for aliases in COUNTER_ALIASES.values() for name in aliases}
    bound_counters = []
    for raw_line in text.splitlines():
        match = PROMETHEUS_LINE_RE.fullmatch(raw_line.strip())
        if not match:
            continue
        labels = _parse_labels(match.group("labels"))
        source_ids = [labels[key] for key in ("fsid", "cluster_fsid") if key in labels]
        try:
            if any(str(UUID(value)) != expected_fsid for value in source_ids):
                raise PerformanceTelemetryError("METRICS_FSID_MISMATCH")
        except (ValueError, AttributeError):
            raise PerformanceTelemetryError("METRICS_FSID_MISMATCH") from None
        if match.group("name") in relevant_names and labels.get("ceph_daemon", "").startswith("osd."):
            bound_counters.append(bool(source_ids))
    if bound_counters and all(bound_counters):
        return "source_fsid_labels"
    endpoint = _metrics_endpoint(configured_url)
    if endpoint is not None and endpoint == _metrics_endpoint(verified_service_url):
        return "verified_ceph_mgr_service_endpoint"
    return "unverified"


def fetch_prometheus_text(
    url: str,
    *,
    timeout_seconds: float = 10.0,
    bearer_token: str | None = None,
) -> str:
    headers = {"Accept": "text/plain; version=0.0.4"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    request = Request(url, headers=headers)
    status = None
    try:
        with _open_prometheus_request(request, timeout_seconds) as response:  # noqa: S310 - URL is operator config
            status = response.status
            content_type = response.headers.get_content_type()
            if content_type not in {"text/plain", "application/openmetrics-text", "application/octet-stream"}:
                raise PerformanceTelemetryError("METRICS_CONTENT_TYPE_INVALID", http_status=status)
            payload = response.read(MAX_PROMETHEUS_BYTES + 1)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        raise PerformanceTelemetryError("METRICS_HTTP_ERROR", http_status=status) from None
    except TimeoutError:
        raise PerformanceTelemetryError("METRICS_TIMEOUT", http_status=status) from None
    except URLError as exc:
        reason = "METRICS_TIMEOUT" if isinstance(exc.reason, TimeoutError) else "METRICS_CONNECTION_FAILED"
        raise PerformanceTelemetryError(reason, http_status=status) from None
    except OSError:
        raise PerformanceTelemetryError("METRICS_CONNECTION_FAILED", http_status=status) from None
    if len(payload) > MAX_PROMETHEUS_BYTES:
        raise PerformanceTelemetryError("METRICS_RESPONSE_TOO_LARGE", http_status=status)
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise PerformanceTelemetryError("METRICS_ENCODING_INVALID", http_status=status) from None
    if not decoded.strip():
        raise PerformanceTelemetryError("METRICS_RESPONSE_EMPTY", http_status=status)
    return PrometheusText(decoded, http_status=status)


def _counter_rates(
    current: dict[str, float],
    previous: dict[str, float] | None,
    elapsed_seconds: float,
) -> tuple[dict[str, float] | None, bool, list[str]]:
    required = set(COUNTER_ALIASES)
    missing = sorted(required - set(current))
    if missing:
        return None, False, ["MISSING_COUNTERS:" + ",".join(missing)]
    if previous is None:
        return None, False, ["WARMING_UP"]
    previous_missing = sorted(required - set(previous))
    if previous_missing:
        return None, False, ["PREVIOUS_SAMPLE_INCOMPLETE"]
    if elapsed_seconds <= 0:
        return None, False, ["NON_MONOTONIC_SAMPLE_TIME"]
    if any(current[key] < previous[key] for key in required):
        return None, True, ["COUNTER_RESET"]
    return (
        {key: (current[key] - previous[key]) / elapsed_seconds for key in required},
        False,
        [],
    )


def counter_sample(
    *,
    fsid: str,
    scope_type: str,
    scope_id: str,
    captured_at: datetime,
    counters: dict[str, float],
    previous_counters: dict[str, float] | None,
    previous_captured_at: datetime | None,
    metric_names: dict[str, str],
    elapsed_seconds: float | None = None,
) -> PerformanceSample:
    elapsed = (
        (captured_at - previous_captured_at).total_seconds()
        if previous_captured_at is not None
        else 0.0
    )
    if elapsed_seconds is not None:
        if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
            raise PerformanceTelemetryError("METRICS_WINDOW_INVALID")
        elapsed = elapsed_seconds
    rates, reset, reasons = _counter_rates(counters, previous_counters, elapsed)
    sample = PerformanceSample(
        fsid=fsid,
        source="ceph",
        scope_type=scope_type,
        scope_id=scope_id,
        captured_at=captured_at,
        window_seconds=elapsed if elapsed > 0 else get_settings().performance_current_window_seconds,
        fresh=True,
        reset_detected=reset,
        partial=rates is None,
        metadata={
            "raw_counters": counters,
            "metric_names": metric_names,
            "reasons": reasons,
            "semantics": "ceph_client_io",
        },
    )
    if rates is not None:
        sample.read_iops = rates["read_ops"]
        sample.write_iops = rates["write_ops"]
        sample.total_iops = sample.read_iops + sample.write_iops
        sample.read_bytes_per_second = rates["read_bytes"]
        sample.write_bytes_per_second = rates["write_bytes"]
        sample.total_bytes_per_second = (
            sample.read_bytes_per_second + sample.write_bytes_per_second
        )
    return sample


def collect_application_sample(
    *,
    captured_at: datetime | None = None,
    db_conn: Any | None = None,
) -> PerformanceSample:
    if db_conn is None:
        with connection() as conn:
            return collect_application_sample(captured_at=captured_at, db_conn=conn)
    settings = get_settings()
    captured_at = captured_at or datetime.now(timezone.utc)
    window_seconds = settings.performance_current_window_seconds
    started_at = captured_at - timedelta(seconds=window_seconds)

    row = db_conn.execute(
        """
        SELECT
          count(*) FILTER (WHERE kind = ANY(%(read_kinds)s)) AS read_count,
          count(*) FILTER (WHERE kind = ANY(%(write_kinds)s)) AS write_count,
          coalesce(sum(bytes_count) FILTER (WHERE kind = ANY(%(read_kinds)s)), 0) AS read_bytes,
          coalesce(sum(bytes_count) FILTER (WHERE kind = ANY(%(write_kinds)s)), 0) AS write_bytes,
          count(*) FILTER (WHERE success) AS success_count,
          count(*) FILTER (WHERE NOT success) AS error_count,
          coalesce(avg(latency_ms), 0) AS average_latency_ms,
          coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms), 0) AS p50_latency_ms,
          coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95_latency_ms,
          coalesce(percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms), 0) AS p99_latency_ms
        FROM operations
        WHERE created_at >= %(started_at)s AND created_at < %(captured_at)s
        """,
        {
            "read_kinds": list(READ_OPERATION_KINDS),
            "write_kinds": list(WRITE_OPERATION_KINDS),
            "started_at": started_at,
            "captured_at": captured_at,
        },
    ).fetchone()

    read_count = int(row["read_count"] or 0)
    write_count = int(row["write_count"] or 0)
    read_bytes = int(row["read_bytes"] or 0)
    write_bytes = int(row["write_bytes"] or 0)
    return PerformanceSample(
        fsid=settings.ceph_expected_fsid or "application",
        source="application",
        scope_type="cluster",
        scope_id="console",
        captured_at=captured_at,
        window_seconds=window_seconds,
        read_iops=read_count / window_seconds,
        write_iops=write_count / window_seconds,
        total_iops=(read_count + write_count) / window_seconds,
        read_bytes_per_second=read_bytes / window_seconds,
        write_bytes_per_second=write_bytes / window_seconds,
        total_bytes_per_second=(read_bytes + write_bytes) / window_seconds,
        average_latency_ms=float(row["average_latency_ms"] or 0),
        p50_latency_ms=float(row["p50_latency_ms"] or 0),
        p95_latency_ms=float(row["p95_latency_ms"] or 0),
        p99_latency_ms=float(row["p99_latency_ms"] or 0),
        success_count=int(row["success_count"] or 0),
        error_count=int(row["error_count"] or 0),
        metadata={
            "semantics": "console_requests",
            "read_operation_kinds": list(READ_OPERATION_KINDS),
            "write_operation_kinds": list(WRITE_OPERATION_KINDS),
        },
    )


SAMPLE_COLUMNS = tuple(
    asdict(PerformanceSample("", "", "", "", datetime.now(timezone.utc), 1)).keys()
)


def store_sample(sample: PerformanceSample, *, db_conn: Any | None = None) -> int:
    if db_conn is None:
        with connection() as conn:
            return store_sample(sample, db_conn=conn)
    values = asdict(sample)
    values["metadata"] = json.dumps(values["metadata"], separators=(",", ":"))
    values["sample_kind"] = "raw"
    columns = ("sample_kind", *SAMPLE_COLUMNS)
    column_sql = ", ".join(columns)
    placeholders = ", ".join(
        f"%({column})s::jsonb" if column == "metadata" else f"%({column})s"
        for column in columns
    )
    row = db_conn.execute(
        f"""
        INSERT INTO performance_samples ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT (
          fsid, sample_kind, source, scope_type, scope_id, captured_at, window_seconds
        ) DO UPDATE SET
          read_iops=excluded.read_iops,
          write_iops=excluded.write_iops,
          total_iops=excluded.total_iops,
          read_bytes_per_second=excluded.read_bytes_per_second,
          write_bytes_per_second=excluded.write_bytes_per_second,
          total_bytes_per_second=excluded.total_bytes_per_second,
          read_latency_ms=excluded.read_latency_ms,
          write_latency_ms=excluded.write_latency_ms,
          average_latency_ms=excluded.average_latency_ms,
          p50_latency_ms=excluded.p50_latency_ms,
          p95_latency_ms=excluded.p95_latency_ms,
          p99_latency_ms=excluded.p99_latency_ms,
          success_count=excluded.success_count,
          error_count=excluded.error_count,
          fresh=excluded.fresh,
          reset_detected=excluded.reset_detected,
          partial=excluded.partial,
          metadata=excluded.metadata
        RETURNING id
        """,
        values,
    ).fetchone()
    return int(row["id"])


def _latest_raw_counter_sample(
    fsid: str,
    scope_type: str,
    scope_id: str,
    *,
    db_conn: Any,
) -> tuple[dict[str, float] | None, datetime | None]:
    row = db_conn.execute(
        """
        SELECT captured_at, metadata
        FROM performance_samples
        WHERE fsid=%s AND sample_kind='raw' AND source='ceph'
          AND scope_type=%s AND scope_id=%s
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (fsid, scope_type, scope_id),
    ).fetchone()
    if not row:
        return None, None
    metadata = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])
    raw = metadata.get("raw_counters")
    if not isinstance(raw, dict):
        return None, row["captured_at"]
    return {key: float(value) for key, value in raw.items()}, row["captured_at"]


def collect_ceph_samples(
    *,
    captured_at: datetime | None = None,
    fetcher=fetch_prometheus_text,
    db_conn: Any | None = None,
) -> list[PerformanceSample]:
    if db_conn is None:
        with connection() as conn:
            return collect_ceph_samples(
                captured_at=captured_at,
                fetcher=fetcher,
                db_conn=conn,
            )
    settings = get_settings()
    if settings.performance_source != "prometheus":
        return []
    if not settings.performance_prometheus_url or not settings.ceph_expected_fsid:
        raise PerformanceTelemetryError("METRICS_NOT_CONFIGURED")
    captured_at = captured_at or datetime.now(timezone.utc)
    if fetcher is fetch_prometheus_text:
        token = (
            settings.performance_prometheus_bearer_token.get_secret_value()
            if settings.performance_prometheus_bearer_token
            else None
        )
        text = fetcher(settings.performance_prometheus_url, bearer_token=token)
    else:
        text = fetcher(settings.performance_prometheus_url)
    try:
        counters_by_osd, metric_names = parse_prometheus_counters(text)
        binding = prometheus_identity_binding(text, settings.ceph_expected_fsid)
    except PerformanceTelemetryError as exc:
        exc.http_status = exc.http_status or getattr(text, "http_status", None)
        raise

    cluster_counters = {
        semantic: sum(values.get(semantic, 0.0) for values in counters_by_osd.values())
        for semantic in COUNTER_ALIASES
        if all(semantic in values for values in counters_by_osd.values())
    }
    scopes: list[tuple[str, str, dict[str, float]]] = [
        ("cluster", settings.ceph_expected_fsid, cluster_counters)
    ]
    scopes.extend(
        ("osd", osd_id, counters)
        for osd_id, counters in sorted(counters_by_osd.items(), key=lambda item: int(item[0]))
    )

    samples: list[PerformanceSample] = []
    for scope_type, scope_id, counters in scopes:
        previous, previous_time = _latest_raw_counter_sample(
            settings.ceph_expected_fsid,
            scope_type,
            scope_id,
            db_conn=db_conn,
        )
        sample = counter_sample(
            fsid=settings.ceph_expected_fsid,
            scope_type=scope_type,
            scope_id=scope_id,
            captured_at=captured_at,
            counters=counters,
            previous_counters=previous,
            previous_captured_at=previous_time,
            metric_names=metric_names,
        )
        sample.metadata["identity_binding"] = binding
        if getattr(text, "http_status", None) is not None:
            sample.metadata["http_status"] = text.http_status
        if binding == "unverified":
            sample.partial = True
            sample.metadata["reasons"].append("TELEMETRY_IDENTITY_UNVERIFIED")
        store_sample(sample, db_conn=db_conn)
        samples.append(sample)
    return samples


def maintain_samples(*, catch_up: bool = False, db_conn: Any | None = None) -> dict[str, int]:
    if db_conn is None:
        with connection() as conn:
            return maintain_samples(catch_up=catch_up, db_conn=conn)
    settings = get_settings()
    rollup_lookback = f"{settings.performance_raw_retention_hours} hours" if catch_up else "10 minutes"
    rollup = db_conn.execute(
            """
            INSERT INTO performance_samples (
              fsid, sample_kind, source, scope_type, scope_id, captured_at, window_seconds,
              read_iops, write_iops, total_iops,
              read_bytes_per_second, write_bytes_per_second, total_bytes_per_second,
              read_latency_ms, write_latency_ms, average_latency_ms,
              p50_latency_ms, p95_latency_ms, p99_latency_ms,
              success_count, error_count, fresh, reset_detected, partial, metadata
            )
            SELECT
              fsid, 'rollup_1m', source, scope_type, scope_id,
              date_trunc('minute', captured_at), 60,
              avg(read_iops), avg(write_iops), avg(total_iops),
              avg(read_bytes_per_second), avg(write_bytes_per_second), avg(total_bytes_per_second),
              avg(read_latency_ms), avg(write_latency_ms), avg(average_latency_ms),
              avg(p50_latency_ms), avg(p95_latency_ms), avg(p99_latency_ms),
              NULL::bigint, NULL::bigint, bool_and(fresh), bool_or(reset_detected),
              bool_or(partial),
              jsonb_build_object('semantics', 'one_minute_average', 'sample_count', count(*))
            FROM performance_samples
            WHERE sample_kind='raw'
              AND captured_at >= now() - CAST(%(lookback)s AS interval)
              AND captured_at < date_trunc('minute', now())
            GROUP BY fsid, source, scope_type, scope_id, date_trunc('minute', captured_at)
            ON CONFLICT (
              fsid, sample_kind, source, scope_type, scope_id, captured_at, window_seconds
            ) DO UPDATE SET
              read_iops=excluded.read_iops,
              write_iops=excluded.write_iops,
              total_iops=excluded.total_iops,
              read_bytes_per_second=excluded.read_bytes_per_second,
              write_bytes_per_second=excluded.write_bytes_per_second,
              total_bytes_per_second=excluded.total_bytes_per_second,
              read_latency_ms=excluded.read_latency_ms,
              write_latency_ms=excluded.write_latency_ms,
              average_latency_ms=excluded.average_latency_ms,
              p50_latency_ms=excluded.p50_latency_ms,
              p95_latency_ms=excluded.p95_latency_ms,
              p99_latency_ms=excluded.p99_latency_ms,
              success_count=NULL,
              error_count=NULL,
              fresh=excluded.fresh,
              reset_detected=excluded.reset_detected,
              partial=excluded.partial,
              metadata=excluded.metadata
            """,
            {"lookback": rollup_lookback},
    ).rowcount
    raw_deleted = db_conn.execute(
            """
            DELETE FROM performance_samples
            WHERE sample_kind='raw'
              AND captured_at < now() - CAST(%(hours)s AS interval)
            """,
            {"hours": f"{settings.performance_raw_retention_hours} hours"},
    ).rowcount
    rollup_deleted = db_conn.execute(
            """
            DELETE FROM performance_samples
            WHERE sample_kind='rollup_1m'
              AND captured_at < now() - CAST(%(days)s AS interval)
            """,
            {"days": f"{settings.performance_rollup_retention_days} days"},
    ).rowcount
    return {
        "rollups_written": max(rollup, 0),
        "raw_deleted": max(raw_deleted, 0),
        "rollups_deleted": max(rollup_deleted, 0),
    }


def collect_performance_once(*, fetcher=fetch_prometheus_text) -> dict[str, Any]:
    settings = get_settings()
    if not settings.performance_enabled:
        return {"enabled": False, "application_samples": 0, "ceph_samples": 0}
    captured_at = datetime.now(timezone.utc)
    application = collect_application_sample(captured_at=captured_at)
    store_sample(application)
    ceph_samples = collect_ceph_samples(captured_at=captured_at, fetcher=fetcher)
    return {
        "enabled": True,
        "captured_at": captured_at.isoformat(),
        "application_samples": 1,
        "ceph_samples": len(ceph_samples),
    }


def serialize_sample(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
    enforce_current_freshness: bool = True,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    captured_at = row["captured_at"]
    settings = get_settings()
    age_seconds = max(0.0, (now - captured_at).total_seconds())
    fresh = bool(row["fresh"]) and (
        not enforce_current_freshness
        or age_seconds <= settings.performance_stale_after_seconds
    )
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    reasons = list(metadata.get("reasons") or [])
    if enforce_current_freshness and not fresh and "STALE_SAMPLE" not in reasons:
        reasons.append("STALE_SAMPLE")
    if row["reset_detected"] and "COUNTER_RESET" not in reasons:
        reasons.append("COUNTER_RESET")
    state = "FRESH"
    if not fresh:
        state = "STALE"
    elif row["partial"]:
        state = "PARTIAL"
    return {
        "schema_version": 1,
        "state": state,
        "source": row["source"],
        "sample_kind": row.get("sample_kind", "raw"),
        "scope_type": row["scope_type"],
        "scope": row["scope_id"],
        "captured_at": captured_at.isoformat(),
        "age_seconds": age_seconds,
        "window_seconds": float(row["window_seconds"]),
        "fresh": fresh,
        "reset_detected": bool(row["reset_detected"]),
        "partial": bool(row["partial"]),
        "iops": {
            "read": row["read_iops"],
            "write": row["write_iops"],
            "total": row["total_iops"],
        },
        "throughput_bps": {
            "read": row["read_bytes_per_second"],
            "write": row["write_bytes_per_second"],
            "total": row["total_bytes_per_second"],
        },
        "latency_ms": {
            "read_avg": row["read_latency_ms"],
            "write_avg": row["write_latency_ms"],
            "average": row["average_latency_ms"],
            "p50": row["p50_latency_ms"],
            "p95": row["p95_latency_ms"],
            "p99": row["p99_latency_ms"],
        },
        "counts": {
            "success": row["success_count"],
            "error": row["error_count"],
        },
        "context": {
            key: value
            for key, value in metadata.items()
            if key not in {"raw_counters", "reasons"}
        },
        "reasons": reasons,
    }


def unavailable_payload(source: str, scope_type: str, scope: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": "UNAVAILABLE",
        "source": source,
        "scope_type": scope_type,
        "scope": scope,
        "captured_at": None,
        "age_seconds": None,
        "window_seconds": None,
        "fresh": False,
        "reset_detected": False,
        "partial": True,
        "iops": {"read": None, "write": None, "total": None},
        "throughput_bps": {"read": None, "write": None, "total": None},
        "latency_ms": {
            "read_avg": None,
            "write_avg": None,
            "average": None,
            "p50": None,
            "p95": None,
            "p99": None,
        },
        "counts": {"success": None, "error": None},
        "context": {},
        "reasons": [reason],
    }


def latest_sample(source: str, scope_type: str, scope: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.performance_enabled:
        return unavailable_payload(source, scope_type, scope, "PERFORMANCE_DISABLED")
    if scope_type not in SUPPORTED_SCOPES.get(source, frozenset()):
        return unavailable_payload(source, scope_type, scope, "UNSUPPORTED_SCOPE")
    if scope_type == "osd" and not scope.isdigit():
        return unavailable_payload(source, scope_type, scope, "INVALID_SCOPE")
    fsid = settings.ceph_expected_fsid or ("application" if source == "application" else "unconfigured")
    with connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM performance_samples
            WHERE fsid=%s AND sample_kind='raw' AND source=%s AND scope_type=%s AND scope_id=%s
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            (fsid, source, scope_type, scope),
        ).fetchone()
    if not row:
        reason = "PERFORMANCE_SOURCE_UNAVAILABLE" if source == "ceph" else "NO_SAMPLES_YET"
        return unavailable_payload(source, scope_type, scope, reason)
    return serialize_sample(row)


def scope_supported(source: str, scope_type: str) -> bool:
    return scope_type in SUPPORTED_SCOPES.get(source, frozenset())


def history_samples(
    source: str,
    scope_type: str,
    scope: str,
    *,
    started_at: datetime,
    ended_at: datetime,
    step_seconds: int,
) -> tuple[str, list[dict[str, Any]]]:
    settings = get_settings()
    fsid = settings.ceph_expected_fsid or ("application" if source == "application" else "unconfigured")
    span = ended_at - started_at
    sample_kind = (
        "rollup_1m"
        if step_seconds >= 60 or span > timedelta(hours=settings.performance_raw_retention_hours)
        else "raw"
    )
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM performance_samples
            WHERE fsid=%s AND sample_kind=%s AND source=%s AND scope_type=%s AND scope_id=%s
              AND captured_at >= %s AND captured_at <= %s
            ORDER BY captured_at ASC
            LIMIT 5000
            """,
            (fsid, sample_kind, source, scope_type, scope, started_at, ended_at),
        ).fetchall()
    # Keep the most recent sample in each requested step. This makes ``step``
    # an actual response-resolution contract instead of a UI-only hint.
    buckets: dict[int, dict[str, Any]] = {}
    for row in rows:
        bucket = int(row["captured_at"].timestamp()) // step_seconds
        buckets[bucket] = row
    return sample_kind, [
        serialize_sample(row, enforce_current_freshness=False)
        for row in buckets.values()
    ]
