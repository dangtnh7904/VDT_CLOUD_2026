#!/usr/bin/env python3
"""Two-minute current RGW smoke probe with an isolated, temporary object."""

import csv
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


run_id = "mon-s3-smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
out = Path("/home/dangg") / run_id
out.mkdir(mode=0o700)
key = f"mon-current/{run_id}/probe.bin"
bucket = "rgw-lab-data"
endpoint = "http://10.20.20.11:8080"
session = boto3.Session(profile_name="rgw-lab")
s3 = session.client("s3", endpoint_url=endpoint,
                    config=Config(connect_timeout=5, read_timeout=10,
                                  retries={"max_attempts": 1},
                                  s3={"addressing_style": "path"}))
manifest = {"run_id": run_id, "at_utc": utc(), "bucket": bucket,
            "endpoint": endpoint, "key": key, "scope": "current S3 smoke only; not 30-minute MON gate"}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
s3.head_bucket(Bucket=bucket)
if s3.get_bucket_versioning(Bucket=bucket).get("Status") in ("Enabled", "Suspended"):
    raise RuntimeError("Bucket versioning prevents simple cleanup")
if s3.list_objects_v2(Bucket=bucket, Prefix=f"mon-current/{run_id}/").get("KeyCount", 0):
    raise RuntimeError("Unexpected existing object under probe prefix")

samples = failures = 0
first = last = None
last_payload = None
start = time.monotonic()
with (out / "s3.csv").open("w", newline="", buffering=1) as handle:
    writer = csv.writer(handle)
    writer.writerow(["at_utc", "rc", "ms", "detail", "sha256"])
    while time.monotonic() - start < 120:
        at = utc()
        first = first or at
        last = at
        t0 = time.monotonic()
        payload = hashlib.sha256(f"{run_id}:{samples}".encode()).digest() * 2048
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=payload)
            actual = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            if actual != payload:
                raise RuntimeError("checksum mismatch")
            rc, detail = 0, "PUT_GET_MATCH"
            last_payload = payload
        except ClientError as exc:
            rc = 1
            detail = "S3:" + exc.response.get("Error", {}).get("Code", "unknown")
            failures += 1
        except Exception as exc:
            rc = 1
            detail = type(exc).__name__
            failures += 1
        writer.writerow([at, rc, round((time.monotonic() - t0) * 1000, 3),
                         detail, hashlib.sha256(payload).hexdigest()])
        samples += 1
        if rc:
            break
        time.sleep(2)

reopen = cleanup = "NOT_RUN"
if failures == 0 and last_payload is not None:
    fresh = boto3.Session(profile_name="rgw-lab").client(
        "s3", endpoint_url=endpoint,
        config=Config(connect_timeout=5, read_timeout=10,
                      retries={"max_attempts": 1},
                      s3={"addressing_style": "path"}))
    actual = fresh.get_object(Bucket=bucket, Key=key)["Body"].read()
    reopen = "PASS" if actual == last_payload else "FAIL"
    if reopen == "PASS":
        fresh.delete_object(Bucket=bucket, Key=key)
        after = fresh.list_objects_v2(Bucket=bucket, Prefix=f"mon-current/{run_id}/")
        cleanup = "PASS" if after.get("KeyCount", 0) == 0 else "FAIL"

summary = {"run_id": run_id, "first": first, "last": last, "ended": utc(),
           "elapsed_seconds": round(time.monotonic() - start, 3),
           "samples": samples, "failures": failures,
           "reopen": reopen, "cleanup": cleanup}
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(out)
print(json.dumps(summary, indent=2))
raise SystemExit(0 if failures == 0 and reopen == "PASS" and cleanup == "PASS" else 4)
