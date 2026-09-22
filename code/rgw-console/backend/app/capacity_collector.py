from __future__ import annotations

import argparse
import json
import logging
import time
from typing import Sequence

from .config import get_settings
from .services.capacity_collector import collect_capacity_once


LOGGER = logging.getLogger("rgw-console-capacity-collector")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect read-only Ceph per-OSD capacity telemetry through the host agent."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect one sample and exit instead of polling continuously.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    interval = get_settings().capacity_collector_interval_seconds
    while True:
        started = time.monotonic()
        try:
            result = collect_capacity_once()
            if args.once:
                print(json.dumps(result, separators=(",", ":"), sort_keys=True))
            else:
                LOGGER.info(
                    "capacity snapshot stored id=%s epoch=%s fresh=%s osds=%s scope_complete=%s released=%s",
                    result["snapshot_id"],
                    result["osdmap_epoch"],
                    result["fresh"],
                    result["osd_count"],
                    result["scope_complete"],
                    len(result["released_reservation_ids"]),
                )
        except Exception as exc:
            # Do not log raw agent details: command errors may include text that
            # should remain on the host. The exception class is enough here.
            LOGGER.error("capacity collection failed error_type=%s", type(exc).__name__)
            if args.once:
                return 1
        if args.once:
            return 0
        elapsed = time.monotonic() - started
        time.sleep(max(0.1, interval - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
