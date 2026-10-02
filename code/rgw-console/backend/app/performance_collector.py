from __future__ import annotations

import logging
import signal
import threading

from .config import get_settings
from .db import initialize, pool
from .services.performance import collect_performance_once, maintain_samples


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("performance-collector")
stop_event = threading.Event()


def _stop(*_args) -> None:
    stop_event.set()


def collect_and_maintain_once() -> None:
    try:
        result = collect_performance_once()
        logger.info("performance collection=%s", result)
    except Exception:
        logger.exception("performance collection failed")

    # Application samples may have been stored before the Ceph scrape failed.
    # Always roll them up so the 1h/24h history keeps advancing.
    try:
        maintenance = maintain_samples()
        logger.info("performance maintenance=%s", maintenance)
    except Exception:
        logger.exception("performance maintenance failed")


def main() -> None:
    settings = get_settings()
    initialize()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        maintain_samples(catch_up=True)
        while not stop_event.is_set():
            collect_and_maintain_once()
            stop_event.wait(settings.performance_collector_interval_seconds)
    finally:
        pool.close()


if __name__ == "__main__":
    main()
