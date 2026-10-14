"""Narrow, non-secret classification of transient database connectivity errors."""
from __future__ import annotations

from psycopg import InterfaceError, OperationalError
from psycopg_pool import PoolClosed, PoolTimeout


class DatabaseUnavailableError(RuntimeError):
    code = "DATABASE_UNAVAILABLE"
    message = "Cơ sở dữ liệu tạm thời chưa sẵn sàng. Vui lòng thử lại."

    def __init__(self):
        # Never include the driver message, SQL, connection string or credentials.
        super().__init__(self.message)


def is_connection_unavailable(exc, connection=None, *, acquiring=False):
    """Keep query, schema, transaction and programming failures visible.

    OperationalError also includes query cancellation and transaction failures,
    so a broad OperationalError-to-503 mapping would hide real application bugs.
    SQLSTATE class 08 and server shutdown/startup codes identify connectivity.
    A driver error without SQLSTATE is transient only at connection acquisition
    or when the actual connection is already closed/broken.
    """
    if isinstance(exc, (PoolTimeout, PoolClosed)):
        return True
    if not isinstance(exc, (OperationalError, InterfaceError)):
        return False
    state = getattr(exc, "sqlstate", None)
    if isinstance(state, str):
        return state.startswith("08") or state in {"57P01", "57P02", "57P03"}
    return state is None and (
        acquiring is True or (connection is not None and (
            getattr(connection, "closed", False) is True
            or getattr(connection, "broken", False) is True)))
