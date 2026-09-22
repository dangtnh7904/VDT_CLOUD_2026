from __future__ import annotations

import argparse
import logging
import time

from .config import get_settings
from .db import initialize, pool
from .services.rbd_lifecycle import RbdLifecycleWorker


LOGGER = logging.getLogger("rgw-console-rbd-lifecycle-worker")


def main() -> None:
    parser = argparse.ArgumentParser(description="Process fenced manual RBD lifecycle actions")
    parser.add_argument("--once", action="store_true", help="Process at most one action")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    initialize()
    try:
        worker = RbdLifecycleWorker()
        while True:
            worked = worker.run_once()
            if args.once:
                return
            if not worked:
                time.sleep(float(get_settings().rbd_action_poll_seconds))
    finally:
        pool.close()


if __name__ == "__main__":
    main()

