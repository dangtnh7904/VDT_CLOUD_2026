import json
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

from psycopg.rows import dict_row
from psycopg import InterfaceError, OperationalError
from psycopg_pool import ConnectionPool

from .config import get_settings
from .migrations.runner import assert_schema_current
from .platform.database_errors import DatabaseUnavailableError, is_connection_unavailable


# Bound waiting for a connection, not execution time of a valid SQL statement.
# The production fault drill previously inherited psycopg_pool's 30s default,
# which produced an unhandled plaintext HTTP 500 when PostgreSQL was stopped.
DATABASE_ACQUIRE_TIMEOUT_SECONDS = 5.0
DATABASE_CONNECT_TIMEOUT_SECONDS = 5


pool = ConnectionPool(
    conninfo=get_settings().database_url,
    min_size=1,
    max_size=10,
    timeout=DATABASE_ACQUIRE_TIMEOUT_SECONDS,
    kwargs={"row_factory": dict_row, "connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS},
    open=False,
)


RGW_OPERATION_KINDS = {"PUT", "GET", "HEAD", "LIST", "UPDATE", "DELETE"}
RBD_FILE_OPERATION_KINDS = {
    "RBD_FILE_READ",
    "RBD_FILE_WRITE",
    "RBD_FILE_DELETE",
}
RBD_OPERATION_KINDS = {
    "RBD_CREATE",
    "RBD_MAP",
    "RBD_FORMAT",
    "RBD_MOUNT",
    *RBD_FILE_OPERATION_KINDS,
    "RBD_UNMOUNT",
    "RBD_UNMAP",
    "RBD_DELETE",
}


def initialize() -> None:
    """Open the pool after the one-shot migration has completed.

    Schema changes deliberately do not run in application or worker startup. Run
    ``python -m app.migrate`` before starting either process.
    """

    conn = None
    try:
        pool.open(wait=True, timeout=DATABASE_ACQUIRE_TIMEOUT_SECONDS)
        with pool.connection(timeout=DATABASE_ACQUIRE_TIMEOUT_SECONDS) as conn:
            assert_schema_current(conn)
    except (OperationalError, InterfaceError) as exc:
        pool.close()
        if is_connection_unavailable(exc, conn, acquiring=conn is None):
            raise DatabaseUnavailableError() from None
        raise
    except Exception:
        pool.close()
        raise


@contextmanager
def connection() -> Iterator[Any]:
    conn = None
    try:
        if pool.closed:
            initialize()
        with pool.connection(timeout=DATABASE_ACQUIRE_TIMEOUT_SECONDS) as conn:
            yield conn
    except (OperationalError, InterfaceError) as exc:
        if is_connection_unavailable(exc, conn, acquiring=conn is None):
            raise DatabaseUnavailableError() from None
        raise


def _rgw_target_id(bucket: str, object_key: str | None) -> str:
    bucket_bytes = len(bucket.encode("utf-8"))
    if object_key is None:
        return f"rgw-bucket:{bucket_bytes}:{bucket}"
    return f"rgw:{bucket_bytes}:{bucket}:{object_key}"


def _set_operation_target_defaults(values: dict[str, Any]) -> None:
    kind = values.get("kind")
    if kind in RGW_OPERATION_KINDS:
        bucket = values.get("bucket")
        object_key = values.get("object_key")
        if bucket is not None:
            values.setdefault(
                "target_type",
                "RGW_BUCKET" if kind == "LIST" and object_key is None else "RGW_OBJECT",
            )
            values.setdefault("target_id", _rgw_target_id(bucket, object_key))
        return

    if kind in RBD_OPERATION_KINDS:
        volume_id = values.get("volume_id")
        if volume_id is not None:
            values.setdefault(
                "target_type",
                "RBD_FILE" if kind in RBD_FILE_OPERATION_KINDS else "RBD_VOLUME",
            )
            values.setdefault("target_id", f"rbd-volume:{volume_id}")


def record_operation(**values: Any) -> None:
    _set_operation_target_defaults(values)
    columns = ", ".join(values)
    placeholders = ", ".join([f"%({key})s" for key in values])
    with connection() as conn:
        conn.execute(f"INSERT INTO operations ({columns}) VALUES ({placeholders})", values)
        conn.commit()


def json_ready(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
    if isinstance(result.get("config"), str):
        result["config"] = json.loads(result["config"])
    return result
