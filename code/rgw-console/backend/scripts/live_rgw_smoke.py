from __future__ import annotations

import argparse
import hashlib
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.storage import client as s3_client


def _require(response, expected: int, step: str):
    if response.status_code != expected:
        body = response.text[:1000]
        raise RuntimeError(f"{step} returned HTTP {response.status_code}: {body}")
    return response


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create, verify, and remove one isolated object in the configured RGW lab scope."
    )
    parser.add_argument(
        "--allow-mutation",
        action="store_true",
        help="Required acknowledgement that the configured bucket is a disposable lab scope.",
    )
    args = parser.parse_args()
    if not args.allow_mutation:
        parser.error("--allow-mutation is required")

    settings = get_settings()
    bucket = settings.rgw_default_bucket
    if bucket not in settings.rgw_allowed_bucket_set:
        raise RuntimeError("RGW_DEFAULT_BUCKET is not present in RGW_ALLOWED_BUCKETS")
    if not settings.rgw_stream_prefix_root:
        raise RuntimeError("RGW_STREAM_PREFIX_ROOT is not configured")

    s3 = s3_client()
    versioning = s3.get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")
    if versioning != "Disabled":
        raise RuntimeError("live smoke refuses versioned/suspended buckets to guarantee cleanup semantics")

    run_id = uuid.uuid4().hex
    key = f"{settings.rgw_stream_prefix_root}smoke/{run_id}.bin"
    payload = (f"rgw-console-live-smoke:{run_id}\n".encode("ascii") * 32)[:1024]
    digest = hashlib.sha256(payload).hexdigest()
    put_succeeded = False

    try:
        with TestClient(app) as api:
            put = _require(
                api.put(
                    "/api/objects/content",
                    params={"bucket": bucket, "key": key},
                    content=payload,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Idempotency-Key": f"smoke-put-{run_id}",
                    },
                ),
                200,
                "PUT",
            )
            put_succeeded = True

            replay = _require(
                api.put(
                    "/api/objects/content",
                    params={"bucket": bucket, "key": key},
                    content=payload,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Idempotency-Key": f"smoke-put-{run_id}",
                    },
                ),
                200,
                "idempotent PUT replay",
            )
            if replay.headers.get("Idempotency-Replayed") != "true":
                raise RuntimeError("repeated PUT was not served from the idempotency record")

            head = _require(
                api.get("/api/objects/head", params={"bucket": bucket, "key": key}),
                200,
                "HEAD",
            ).json()
            if int(head.get("size", -1)) != len(payload):
                raise RuntimeError("HEAD returned an unexpected object size")

            downloaded = _require(
                api.get("/api/objects/content", params={"bucket": bucket, "key": key}),
                200,
                "GET",
            ).content
            if hashlib.sha256(downloaded).hexdigest() != digest:
                raise RuntimeError("GET checksum does not match the uploaded payload")

            deleted = _require(
                api.delete(
                    "/api/objects",
                    params={"bucket": bucket, "key": key},
                    headers={"Idempotency-Key": f"smoke-delete-{run_id}"},
                ),
                200,
                "DELETE",
            ).json()
            if not deleted.get("hard_delete"):
                raise RuntimeError("DELETE was not reported as an unversioned hard delete")
            put_succeeded = False

        print(f"live RGW smoke passed: bucket={bucket} key={key} bytes={len(payload)} sha256={digest}")
        return 0
    finally:
        if put_succeeded:
            # The preflight above guarantees unversioned cleanup. This fallback
            # runs only when a validation step fails after PUT succeeded.
            s3.delete_object(Bucket=bucket, Key=key)


if __name__ == "__main__":
    raise SystemExit(main())
