from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence

import psycopg
from psycopg.rows import dict_row

from .config import get_settings
from .migrations.runner import MigrationError, assert_schema_current, migrate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply the RGW/RBD console PostgreSQL migrations."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that all migrations are applied without changing the database",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0,
        help="wait up to this many seconds for PostgreSQL to become reachable",
    )
    parser.add_argument(
        "--retry-interval",
        type=float,
        default=1,
        help="seconds between PostgreSQL connection attempts when --wait-seconds is used",
    )
    return parser


def _connect(wait_seconds: float, retry_interval: float):
    if wait_seconds < 0:
        raise ValueError("--wait-seconds must be non-negative")
    if retry_interval <= 0:
        raise ValueError("--retry-interval must be greater than zero")

    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return psycopg.connect(
                get_settings().database_url,
                row_factory=dict_row,
                connect_timeout=max(1, min(10, int(wait_seconds) or 5)),
            )
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(retry_interval, max(0, deadline - time.monotonic())))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        with _connect(args.wait_seconds, args.retry_interval) as conn:
            if args.check:
                version = assert_schema_current(conn)
                print(f"Database schema is current at version {version:04d}.")
                return 0

            result = migrate(conn)
            applied = ", ".join(f"{version:04d}" for version in result.applied_versions)
            stamped = ", ".join(f"{version:04d}" for version in result.stamped_versions)
            if stamped:
                print(f"Stamped supported legacy baseline: {stamped}.")
            if applied:
                print(f"Applied migrations: {applied}.")
            else:
                print("No pending migrations.")
            print(f"Database schema is current at version {result.current_version:04d}.")
            return 0
    except (MigrationError, psycopg.Error, ValueError) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
