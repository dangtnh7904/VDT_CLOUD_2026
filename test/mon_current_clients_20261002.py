#!/usr/bin/env python3
"""Run isolated current-state CephX, RBD and RGW probes for 32 minutes.

Run as root on ceph-master only from mon_current_soak_20261002.sh. The test
creates one uniquely named 64 MiB RBD image and one 64 KiB S3 object in the
existing lab pool/bucket, then verifies and attempts cleanup even on failure.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import rados
import rbd
from botocore.config import Config
from botocore.exceptions import ClientError


CONF = "/tmp/ceph-client.conf"
KEYRING = "/tmp/client.keyring"
POOL = "rbd-lab"
ENDPOINT = "http://10.20.20.11:8080"
BUCKET = "rgw-lab-data"
PROFILE = "rgw-lab"
EXPECTED_FSID = "17c77e12-a16a-11f1-838e-cf68e9c001d8"
DURATION_SECONDS = 1920
stop_event = threading.Event()
deadline = 0.0


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def safe_error(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "unknown")
        return f"S3:{code}"
    errno = getattr(exc, "errno", None)
    if errno is not None:
        return f"{type(exc).__name__}:{errno}"
    if isinstance(exc, ProbeError):
        return exc.code
    if isinstance(exc, subprocess.TimeoutExpired):
        return "CephCLI:timeout"
    return type(exc).__name__


class ProbeError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def ceph_client() -> rados.Rados:
    client = rados.Rados(conffile=CONF, name="client.admin")
    try:
        client.conf_set("keyring", KEYRING)
        client.conf_set("rbd_cache", "false")
        client.conf_set("rados_osd_op_timeout", "10")
        client.conf_set("rados_mon_op_timeout", "10")
        client.connect()
        if client.get_fsid() != EXPECTED_FSID:
            raise ProbeError("RBD_CLIENT_FSID_MISMATCH")
    except Exception:
        client.shutdown()
        raise
    return client


def csv_probe(path: Path, worker: callable) -> dict:
    started = utc()
    samples = failures = 0
    first = last = None
    previous_start = None
    max_start_gap_seconds = 0.0
    with path.open("w", newline="", buffering=1) as handle:
        writer = csv.writer(handle)
        writer.writerow(["at_utc", "end_utc", "rc", "ms", "detail"])
        while time.monotonic() < deadline and not stop_event.is_set():
            at = utc()
            first = first or at
            t0 = time.monotonic()
            if previous_start is not None:
                max_start_gap_seconds = max(max_start_gap_seconds, t0 - previous_start)
            previous_start = t0
            try:
                detail = worker(samples)
                rc = 0
            except Exception as exc:  # Keep the run alive long enough to record failure.
                detail = safe_error(exc)
                rc = 1
                failures += 1
            ms = round((time.monotonic() - t0) * 1000, 3)
            last = utc()
            writer.writerow([at, last, rc, ms, detail])
            samples += 1
            stop_event.wait(5 if path.name == "auth.csv" else 2)
    return {"started": started, "first": first, "last": last,
            "ended": utc(), "samples": samples, "failures": failures,
            "max_start_gap_seconds": round(max_start_gap_seconds, 3)}


def main() -> int:
    if os.geteuid() != 0 or len(sys.argv) != 2:
        print("Run as root with one evidence-directory argument", file=sys.stderr)
        return 2
    out = Path(sys.argv[1]).resolve()
    run_id = out.name
    if not re.fullmatch(r"mon-current-\d{8}T\d{6}Z-[A-Za-z0-9]+", run_id):
        print("Unexpected run ID", file=sys.stderr)
        return 2
    if not out.is_dir():
        print("Evidence directory does not exist", file=sys.stderr)
        return 2

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    key = f"mon-current/{run_id}/probe.bin"
    image = run_id
    manifest = {"run_id": run_id, "rbd_pool": POOL, "rbd_image": image,
                "s3_endpoint": ENDPOINT, "s3_bucket": BUCKET, "s3_key": key,
                "client_config": CONF, "client_keyring_path": KEYRING,
                "expected_fsid": EXPECTED_FSID,
                "scope": "current-state only; not historical rollout evidence"}
    save_json(out / "client-manifest.json", manifest)
    latest_blocks: dict[int, str] = {}
    latest_s3: bytes | None = None
    results: dict[str, dict] = {}
    verification = {"at": utc(), "rbd_reopen": "NOT_RUN", "s3_reopen": "NOT_RUN",
                    "rbd_cleanup": "NOT_RUN", "s3_cleanup": "NOT_RUN"}
    image_create_attempted = False
    s3_write_attempted = False
    s3 = None
    phase = "preflight"
    run_error = None

    def s3_key_missing() -> bool:
        if s3 is None:
            raise ProbeError("S3_CLIENT_NOT_READY")
        try:
            s3.head_object(Bucket=BUCKET, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return True
            raise
        return False

    def auth_once(_: int) -> str:
        result = subprocess.run(
            ["timeout", "--kill-after=5s", "25s", "ceph", "--conf", CONF,
             "--keyring", KEYRING, "--name", "client.admin", "-s", "--format", "json"],
            capture_output=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            raise ProbeError(f"CEPH_STATUS_RC_{result.returncode}")
        payload = json.loads(result.stdout)
        health = payload.get("health", {}).get("status")
        if not isinstance(health, str):
            raise ProbeError("CEPH_STATUS_MISSING_HEALTH")
        return health

    def rbd_once(n: int) -> str:
        offset = (n % 256) * 4096
        payload = hashlib.sha256(f"{run_id}:{n}".encode()).digest() * 128
        client = ceph_client()
        try:
            with client.open_ioctx(POOL) as ioctx:
                with rbd.Image(ioctx, image) as im:
                    written = im.write(payload, offset)
                    if written is not None and written != len(payload):
                        raise ProbeError("RBD_SHORT_WRITE")
                    im.flush()
                    if im.read(offset, len(payload)) != payload:
                        raise ProbeError("RBD_CHECKSUM_MISMATCH")
        finally:
            client.shutdown()
        latest_blocks[offset] = hashlib.sha256(payload).hexdigest()
        return str(offset)

    def s3_once(n: int) -> str:
        nonlocal latest_s3, s3_write_attempted
        payload = hashlib.sha256(f"{run_id}:{n}".encode()).digest() * 2048
        s3_write_attempted = True
        s3.put_object(Bucket=BUCKET, Key=key, Body=payload)
        actual = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        if actual != payload:
            raise ProbeError("S3_CHECKSUM_MISMATCH")
        latest_s3 = payload
        return str(n)

    def run_worker(name: str, worker: callable) -> None:
        try:
            results[name] = csv_probe(out / f"{name}.csv", worker)
        except Exception as exc:
            results[name] = {"samples": 0, "failures": 1,
                             "fatal_error": safe_error(exc)}

    try:
        for source in (CONF, KEYRING, "/home/dangg/.aws/config",
                       "/home/dangg/.aws/credentials"):
            if not os.path.isfile(source) or not os.access(source, os.R_OK):
                raise ProbeError(f"MISSING_CLIENT_FILE:{source}")
        os.environ["AWS_CONFIG_FILE"] = "/home/dangg/.aws/config"
        os.environ["AWS_SHARED_CREDENTIALS_FILE"] = "/home/dangg/.aws/credentials"
        session = boto3.Session(profile_name=PROFILE)
        s3 = session.client(
            "s3", endpoint_url=ENDPOINT,
            config=Config(connect_timeout=5, read_timeout=10,
                          retries={"max_attempts": 1},
                          s3={"addressing_style": "path"}),
        )
        s3.head_bucket(Bucket=BUCKET)
        versioning = s3.get_bucket_versioning(Bucket=BUCKET).get("Status", "")
        if versioning in ("Enabled", "Suspended"):
            raise ProbeError("S3_BUCKET_VERSIONED")
        if not s3_key_missing():
            raise ProbeError("S3_TEST_KEY_ALREADY_EXISTS")

        client = ceph_client()  # Checks the client-side FSID before any RBD mutation.
        try:
            with client.open_ioctx(POOL) as ioctx:
                if image in rbd.RBD().list(ioctx):
                    raise ProbeError("RBD_TEST_IMAGE_ALREADY_EXISTS")
                if stop_event.is_set():
                    raise ProbeError("STOP_REQUESTED_DURING_PREFLIGHT")
                image_create_attempted = True
                rbd.RBD().create(ioctx, image, size=64 * 1024 * 1024)
        finally:
            client.shutdown()

        if stop_event.is_set():
            raise ProbeError("STOP_REQUESTED_DURING_PREFLIGHT")
        save_json(out / "client-ready.json", {"at": utc(), **manifest})
        global deadline
        deadline = time.monotonic() + DURATION_SECONDS
        phase = "run"
        threads = [
            threading.Thread(target=run_worker, args=("auth", auth_once)),
            threading.Thread(target=run_worker, args=("rbd", rbd_once)),
            threading.Thread(target=run_worker, args=("s3", s3_once)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    except Exception as exc:
        run_error = safe_error(exc)
        save_json(out / "client-failed.json", {"at": utc(), "phase": phase,
                                                "reason": run_error})
    finally:
        phase = "verification_and_cleanup"
        if latest_blocks:
            try:
                client = ceph_client()
                try:
                    with client.open_ioctx(POOL) as ioctx:
                        with rbd.Image(ioctx, image) as im:
                            for offset, expected in latest_blocks.items():
                                actual = hashlib.sha256(im.read(offset, 4096)).hexdigest()
                                if actual != expected:
                                    raise ProbeError("RBD_FINAL_REOPEN_CHECKSUM_MISMATCH")
                        verification["rbd_reopen"] = f"PASS {len(latest_blocks)} blocks"
                finally:
                    client.shutdown()
            except Exception as exc:
                verification["rbd_reopen"] = safe_error(exc)
        if latest_s3 is not None and s3 is not None:
            try:
                actual = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
                if actual != latest_s3:
                    raise ProbeError("S3_FINAL_REOPEN_CHECKSUM_MISMATCH")
                verification["s3_reopen"] = "PASS"
            except Exception as exc:
                verification["s3_reopen"] = safe_error(exc)

        if image_create_attempted:
            try:
                client = ceph_client()
                try:
                    with client.open_ioctx(POOL) as ioctx:
                        if image in rbd.RBD().list(ioctx):
                            rbd.RBD().remove(ioctx, image)
                        if image in rbd.RBD().list(ioctx):
                            raise ProbeError("RBD_CLEANUP_IMAGE_STILL_PRESENT")
                    verification["rbd_cleanup"] = "PASS"
                finally:
                    client.shutdown()
            except Exception as exc:
                verification["rbd_cleanup"] = safe_error(exc)
        if s3_write_attempted and s3 is not None:
            try:
                s3.delete_object(Bucket=BUCKET, Key=key)
                if not s3_key_missing():
                    raise ProbeError("S3_CLEANUP_OBJECT_STILL_PRESENT")
                verification["s3_cleanup"] = "PASS"
            except Exception as exc:
                verification["s3_cleanup"] = safe_error(exc)

    workers_pass = set(results) == {"auth", "rbd", "s3"} and all(
        item.get("failures") == 0 and item.get("samples", 0) > 1 and
        item.get("max_start_gap_seconds", float("inf")) <= 30 and
        item.get("first") is not None and item.get("last") is not None and
        (datetime.fromisoformat(item["last"].replace("Z", "+00:00")) -
         datetime.fromisoformat(item["first"].replace("Z", "+00:00"))).total_seconds() >= 1800
        for item in results.values()
    )
    cleanup_pass = all(verification[key].startswith("PASS") for key in
                       ("rbd_reopen", "s3_reopen", "rbd_cleanup", "s3_cleanup"))
    client_pass = run_error is None and not stop_event.is_set() and workers_pass and cleanup_pass
    save_json(out / "client-summary.json", {"at": utc(), "workers": results,
                                             "verification": verification,
                                             "stop_requested": stop_event.is_set(),
                                             "run_error": run_error,
                                             "client_pass": client_pass})
    return 0 if client_pass else 4


if __name__ == "__main__":
    raise SystemExit(main())
