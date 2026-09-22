from __future__ import annotations

import mimetypes
import random
import signal
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings
from .corpus import choose_random, classify
from .db import connection, initialize, json_ready, pool, record_operation
from .services.capacity_guard import CapacityRejected, finish_reservation, require_admission, require_cleanup_admission, reservation_lease
from .services.scope_validator import ScopeValidator
from .storage import client as s3_client
from .storage import delete_exact, exact_put, object_key, upload_file


running = True
worker_id = f"{socket.gethostname()}-{uuid.uuid4()}"
scope_validator = ScopeValidator()


class LeaseLost(RuntimeError):
    pass


def shutdown(*_):
    global running
    running = False


def _lease_seconds() -> int:
    return int(get_settings().capacity_operation_lease_seconds)


def get_job() -> dict[str, Any] | None:
    """Atomically claim one job and advance its fencing generation."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE stream_jobs
               SET state='paused',
                   paused_reason='LEASE_EXPIRED_RECONCILE_REQUIRED',
                   updated_at=now()
             WHERE state='running' AND lease_expires_at < now()
            """
        )
        row = conn.execute(
            """
            WITH candidate AS (
              SELECT id FROM stream_jobs
               WHERE state='pending'
               ORDER BY created_at
               FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE stream_jobs AS job
               SET state='running', lease_owner=%s,
                   lease_generation=job.lease_generation+1,
                   lease_expires_at=now() + (%s * interval '1 second'),
                   heartbeat_at=now(), started_at=coalesce(job.started_at,now()),
                   paused_reason=NULL, updated_at=now()
              FROM candidate
             WHERE job.id=candidate.id
            RETURNING job.*
            """,
            (worker_id, _lease_seconds()),
        ).fetchone()
        conn.commit()
    return json_ready(row) if row else None


def heartbeat(job_id: str, generation: int) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE stream_jobs
               SET heartbeat_at=now(),
                   lease_expires_at=now() + (%s * interval '1 second'),
                   updated_at=now()
             WHERE id=%s AND lease_owner=%s AND lease_generation=%s
               AND state IN ('running','paused','stopping')
            RETURNING id
            """,
            (_lease_seconds(), job_id, worker_id, generation),
        ).fetchone()
        conn.commit()
    return bool(row)


def assert_lease(job_id: str, generation: int, *, mutation: bool = False) -> str:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT state, lease_expires_at > now() AS lease_valid
              FROM stream_jobs
             WHERE id=%s AND lease_owner=%s AND lease_generation=%s
            """,
            (job_id, worker_id, generation),
        ).fetchone()
    if not row or not row["lease_valid"]:
        raise LeaseLost("job lease/fencing generation is no longer valid")
    if mutation and row["state"] != "running":
        raise LeaseLost(f"job state {row['state']} does not allow mutation")
    return row["state"]


def state_of(job_id: str, generation: int) -> str:
    try:
        return assert_lease(job_id, generation)
    except LeaseLost:
        return "lease_lost"


def set_state(job_id: str, generation: int, state: str, error: str | None = None, paused_reason: str | None = None) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE stream_jobs
               SET state=%s, last_error=coalesce(%s,last_error), paused_reason=%s,
                   updated_at=now(),
                   finished_at=CASE WHEN %s IN ('completed','stopped','failed') THEN now() ELSE finished_at END,
                   lease_expires_at=CASE WHEN %s IN ('completed','stopped','failed') THEN NULL ELSE lease_expires_at END
             WHERE id=%s AND lease_owner=%s AND lease_generation=%s
            RETURNING id
            """,
            (state, error, paused_reason, state, state, job_id, worker_id, generation),
        ).fetchone()
        conn.commit()
    return bool(row)


def add_result(job_id: str, generation: int, result: dict[str, Any]) -> None:
    operation = str(result.get("operation") or "PUT").upper()
    success = bool(result.get("success"))
    byte_count = int(result.get("size") or result.get("bytes") or 0) if success else 0
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE stream_jobs
               SET sent_count=sent_count+%s, failed_count=failed_count+%s,
                   bytes_sent=bytes_sent+%s, last_error=coalesce(%s,last_error),
                   operation_counts=operation_counts || jsonb_build_object(
                       %s, coalesce((operation_counts->>%s)::bigint,0)+1),
                   operation_bytes=operation_bytes || jsonb_build_object(
                       %s, coalesce((operation_bytes->>%s)::bigint,0)+%s),
                   updated_at=now()
             WHERE id=%s AND lease_owner=%s AND lease_generation=%s
               AND lease_expires_at > now()
            RETURNING id
            """,
            (
                1 if success else 0, 0 if success else 1, byte_count,
                result.get("error"), operation, operation, operation, operation,
                byte_count, job_id, worker_id, generation,
            ),
        ).fetchone()
        conn.commit()
    if not row:
        raise LeaseLost("result rejected by job fencing generation")


def weighted_choice(weights: dict[str, float]) -> str | None:
    usable = [(str(name).upper(), float(weight)) for name, weight in weights.items() if float(weight) > 0]
    return random.choices([item[0] for item in usable], weights=[item[1] for item in usable], k=1)[0] if usable else None


def weighted_category(weights: dict[str, float]) -> str | None:
    choice = weighted_choice(weights)
    return choice.lower() if choice else None


def _choose_payload(config: dict[str, Any]) -> tuple[Path, str]:
    category = weighted_category(config.get("weights", {}))
    try:
        _, _, path = choose_random(config.get("corpus_ids", ["mixed"]), category, None, None, None)
    except Exception:
        _, _, path = choose_random(config.get("corpus_ids", ["mixed"]), None, None, None, None)
    return path, classify(path)


def _catalog_object(
    job_id: str,
    generation: int,
    bucket: str,
    result: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
) -> None:
    version_id = result.get("version_id")
    synthetic_id = None if version_id else str(uuid.uuid4())
    with connection() as conn:
        if previous is not None:
            previous_is_versioned = bool(previous.get("version_id"))
            released = conn.execute(
                """
                UPDATE stream_objects
                   SET state=%s,
                       deleted_at=CASE WHEN %s='DELETED' THEN now() ELSE deleted_at END,
                       claim_owner=NULL, claim_generation=NULL, claim_expires_at=NULL,
                       updated_at=now()
                 WHERE id=%s AND claim_owner=%s AND claim_generation=%s
                   AND state='UPDATING'
                RETURNING id
                """,
                (
                    "LIVE" if previous_is_versioned else "DELETED",
                    "LIVE" if previous_is_versioned else "DELETED",
                    previous["id"], worker_id, generation,
                ),
            ).fetchone()
            if not released:
                raise LeaseLost("update catalog claim was lost before commit")
        row = conn.execute(
            """
            INSERT INTO stream_objects (
              job_id,bucket,object_key,version_id,synthetic_unversioned_id,
              is_delete_marker,size_bytes,etag,state
            ) VALUES (%s,%s,%s,%s,%s,false,%s,%s,'LIVE') RETURNING id
            """,
            (job_id, bucket, result["key"], version_id, synthetic_id, int(result.get("size") or 0), result.get("etag")),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO stream_object_heads (bucket,object_key,stream_object_id,updated_at)
            VALUES (%s,%s,%s,now())
            ON CONFLICT (bucket,object_key)
            DO UPDATE SET stream_object_id=excluded.stream_object_id, updated_at=now()
            """,
            (bucket, result["key"], row["id"]),
        )
        conn.commit()


def _pick_head(job_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT obj.* FROM stream_objects obj
              JOIN stream_object_heads head ON head.stream_object_id=obj.id
             WHERE obj.job_id=%s AND obj.state='LIVE' AND NOT obj.is_delete_marker
             ORDER BY random() LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def _claim_head(job_id: str, generation: int, target_state: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            WITH candidate AS (
              SELECT obj.id FROM stream_objects obj
                JOIN stream_object_heads head ON head.stream_object_id=obj.id
               WHERE obj.job_id=%s AND obj.state='LIVE' AND NOT obj.is_delete_marker
               ORDER BY random()
               FOR UPDATE OF obj SKIP LOCKED LIMIT 1
            )
            UPDATE stream_objects obj
               SET state=%s, claim_owner=%s, claim_generation=%s,
                   claim_expires_at=now() + (%s * interval '1 second'),
                   updated_at=now()
              FROM candidate
             WHERE obj.id=candidate.id
            RETURNING obj.*
            """,
            (job_id, target_state, worker_id, generation, _lease_seconds()),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def _claim_any_live(job_id: str, generation: int, target_state: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            WITH candidate AS (
              SELECT id FROM stream_objects
               WHERE job_id=%s AND state='LIVE'
               ORDER BY created_at DESC,id DESC
               FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE stream_objects obj
               SET state=%s, claim_owner=%s, claim_generation=%s,
                   claim_expires_at=now() + (%s * interval '1 second'),
                   updated_at=now()
              FROM candidate
             WHERE obj.id=candidate.id
            RETURNING obj.*
            """,
            (job_id, target_state, worker_id, generation, _lease_seconds()),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def _release_object_claim(obj: dict[str, Any], generation: int) -> None:
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE stream_objects
               SET state='LIVE', claim_owner=NULL, claim_generation=NULL,
                   claim_expires_at=NULL, updated_at=now()
             WHERE id=%s AND state IN ('UPDATING','DELETING')
               AND claim_owner=%s AND claim_generation=%s
            RETURNING id
            """,
            (obj["id"], worker_id, generation),
        ).fetchone()
        conn.commit()
    if not row:
        raise LeaseLost("object claim is no longer owned by this worker generation")


def _live_totals(job_id: str) -> tuple[int, int]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT count(*) AS objects, coalesce(sum(obj.size_bytes),0) AS bytes
              FROM stream_objects obj
              JOIN stream_object_heads head ON head.stream_object_id=obj.id
             WHERE obj.job_id=%s AND obj.state='LIVE' AND NOT obj.is_delete_marker
            """,
            (job_id,),
        ).fetchone()
    return int(row["objects"]), int(row["bytes"])


def _record_read(kind: str, job_id: str, bucket: str, key: str, started: float, *, size: int = 0, success: bool = True, error: str | None = None) -> dict[str, Any]:
    record_operation(
        kind=kind, success=success, bytes_count=size if success else 0,
        latency_ms=(time.perf_counter() - started) * 1000,
        bucket=bucket, object_key=key, client_id=None, category=None,
        source="streaming", content_type=None, error=error, job_id=job_id,
        error_code=None if success else f"RGW_{kind}_FAILED",
    )
    return {"success": success, "operation": kind, "size": size, "error": error}


def _put(job_id: str, generation: int, config: dict[str, Any], *, update: dict[str, Any] | None = None) -> dict[str, Any]:
    operation = "UPDATE" if update else "PUT"
    rgw_succeeded = False
    mutation_started = False
    decision = None
    try:
        path, category = _choose_payload(config)
        key = update["object_key"] if update else object_key(
            config["client_id"], "stream", category, path.name,
            config.get("prefix", ""), naming_strategy=config.get("naming_strategy", "generated"),
            root_prefix=config.get("stream_root", ""),
        )
        scope_validator.require_key(config["bucket"], key, streaming=True)
        assert_lease(job_id, generation, mutation=True)
        decision = require_admission(operation, path.stat().st_size, job_id=job_id)
        with reservation_lease(decision):
            assert_lease(job_id, generation, mutation=True)
            with path.open("rb") as body:
                mutation_started = True
                result = exact_put(
                    body, path.stat().st_size, config["bucket"], key,
                    content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    metadata={"client-id": config["client_id"], "category": category, "source": "streaming", "original-name": path.name},
                    job_id=job_id, capacity_decision_id=decision.id, source="streaming",
                )
        rgw_succeeded = True
        finish_reservation(decision, "success")
        result["operation"] = operation
        _catalog_object(job_id, generation, config["bucket"], result, previous=update)
        return result
    except Exception:
        if decision is not None:
            try:
                finish_reservation(decision, "ambiguous" if mutation_started else "not_started")
            except Exception:
                pass
        if update and not mutation_started:
            _release_object_claim(update, generation)
        raise


def _get(job_id: str, generation: int, config: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    assert_lease(job_id, generation)
    params = {"Bucket": config["bucket"], "Key": obj["object_key"]}
    if obj.get("version_id"):
        params["VersionId"] = obj["version_id"]
    started = time.perf_counter()
    try:
        response = s3_client().get_object(**params)
        size = sum(len(chunk or b"") for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024))
        return _record_read("GET", job_id, config["bucket"], obj["object_key"], started, size=size)
    except Exception as exc:
        return _record_read("GET", job_id, config["bucket"], obj["object_key"], started, success=False, error=str(exc)[:1000])


def _head(job_id: str, generation: int, config: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    assert_lease(job_id, generation)
    params = {"Bucket": config["bucket"], "Key": obj["object_key"]}
    if obj.get("version_id"):
        params["VersionId"] = obj["version_id"]
    started = time.perf_counter()
    try:
        response = s3_client().head_object(**params)
        return _record_read("HEAD", job_id, config["bucket"], obj["object_key"], started, size=int(response.get("ContentLength") or 0))
    except Exception as exc:
        return _record_read("HEAD", job_id, config["bucket"], obj["object_key"], started, success=False, error=str(exc)[:1000])


def _list(job_id: str, generation: int, config: dict[str, Any]) -> dict[str, Any]:
    assert_lease(job_id, generation)
    prefix = config.get("scope_prefix") or config.get("stream_root", "")
    scope_validator.require_prefix(config["bucket"], prefix, streaming=True)
    started = time.perf_counter()
    try:
        response = s3_client().list_objects_v2(Bucket=config["bucket"], Prefix=prefix, MaxKeys=100)
        return _record_read("LIST", job_id, config["bucket"], prefix, started, size=len(response.get("Contents", [])))
    except Exception as exc:
        return _record_read("LIST", job_id, config["bucket"], prefix, started, success=False, error=str(exc)[:1000])


def _delete(job_id: str, generation: int, config: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    rgw_succeeded = False
    mutation_started = False
    decision = None
    try:
        assert_lease(job_id, generation, mutation=True)
        scope_validator.require_key(config["bucket"], obj["object_key"], streaming=True)
        decision = require_cleanup_admission(job_id=job_id)
        with reservation_lease(decision):
            assert_lease(job_id, generation, mutation=True)
            mutation_started = True
            result = delete_exact(config["bucket"], obj["object_key"], version_id=obj.get("version_id"), source="streaming")
        rgw_succeeded = True
        finish_reservation(decision, "success")
    except Exception:
        if decision is not None:
            try:
                finish_reservation(decision, "ambiguous" if mutation_started else "not_started")
            except Exception:
                pass
        if not mutation_started:
            _release_object_claim(obj, generation)
        raise
    result.update({"operation": "DELETE", "size": 0})
    with connection() as conn:
        released = conn.execute(
            """
            UPDATE stream_objects
               SET state='DELETED', deleted_at=now(), claim_owner=NULL,
                   claim_generation=NULL, claim_expires_at=NULL, updated_at=now()
             WHERE id=%s AND state='DELETING' AND claim_owner=%s AND claim_generation=%s
            RETURNING id
            """,
            (obj["id"], worker_id, generation),
        ).fetchone()
        if not released:
            raise LeaseLost("delete catalog claim was lost after RGW mutation")
        next_head = conn.execute(
            """SELECT id FROM stream_objects
                 WHERE job_id=%s AND bucket=%s AND object_key=%s AND state='LIVE'
                 ORDER BY created_at DESC,id DESC LIMIT 1""",
            (job_id, config["bucket"], obj["object_key"]),
        ).fetchone()
        if next_head:
            conn.execute("UPDATE stream_object_heads SET stream_object_id=%s,updated_at=now() WHERE bucket=%s AND object_key=%s", (next_head["id"], config["bucket"], obj["object_key"]))
        else:
            conn.execute("DELETE FROM stream_object_heads WHERE bucket=%s AND object_key=%s", (config["bucket"], obj["object_key"]))
        conn.commit()
    return result


def perform_crud(job_id: str, generation: int, config: dict[str, Any]) -> dict[str, Any]:
    operation = weighted_choice(config.get("operation_weights", {})) or "PUT"
    live_objects, live_bytes = _live_totals(job_id)
    obj = _pick_head(job_id)
    if operation == "PUT" and (
        live_objects >= int(config.get("max_live_objects", 10_000))
        or live_bytes >= int(config.get("max_live_logical_bytes", 10 * 1024**3))
    ):
        operation = "DELETE" if obj and config.get("auto_drain", True) else "GET" if obj else "LIST"
    if operation in {"GET", "HEAD", "UPDATE", "DELETE"} and obj is None:
        operation = "PUT" if live_objects < int(config.get("max_live_objects", 10_000)) else "LIST"
    if operation == "UPDATE":
        obj = _claim_head(job_id, generation, "UPDATING")
        if obj is None:
            operation = "PUT"
    elif operation == "DELETE":
        obj = _claim_head(job_id, generation, "DELETING")
        if obj is None:
            operation = "LIST"
    try:
        if operation == "PUT":
            return _put(job_id, generation, config)
        if operation == "UPDATE":
            return _put(job_id, generation, config, update=obj)
        if operation == "GET":
            return _get(job_id, generation, config, obj)
        if operation == "HEAD":
            return _head(job_id, generation, config, obj)
        if operation == "DELETE":
            return _delete(job_id, generation, config, obj)
        return _list(job_id, generation, config)
    except CapacityRejected as exc:
        if operation == "DELETE":
            result = _list(job_id, generation, config)
            result["fallback_reason"] = exc.decision.state
            return result
        claimed = _claim_head(job_id, generation, "DELETING") if config.get("auto_drain", True) else None
        if claimed:
            result = _delete(job_id, generation, config, claimed)
            result["fallback_reason"] = exc.decision.state
            return result
        result = _list(job_id, generation, config)
        result["fallback_reason"] = exc.decision.state
        return result


def put_one_legacy(job_id: str, generation: int, config: dict[str, Any]) -> dict[str, Any]:
    path, category = _choose_payload(config)
    key = object_key(
        config["client_id"], "stream", category, path.name, config.get("prefix", ""),
        naming_strategy=config.get("naming_strategy", "generated"), root_prefix=config.get("stream_root", ""),
    )
    scope_validator.require_key(config["bucket"], key, streaming=True)
    assert_lease(job_id, generation, mutation=True)
    decision = require_admission("PUT", path.stat().st_size, job_id=job_id)
    mutation_started = False
    try:
        with reservation_lease(decision):
            assert_lease(job_id, generation, mutation=True)
            mutation_started = True
            result = upload_file(path, config["bucket"], key, config["client_id"], category, "streaming", job_id=job_id, capacity_decision_id=decision.id)
        finish_reservation(decision, "success")
        result["operation"] = "PUT"
        return result
    except Exception as exc:
        try:
            finish_reservation(decision, "ambiguous" if mutation_started else "not_started")
        except Exception:
            pass
        if mutation_started:
            raise
        return {"success": False, "operation": "PUT", "size": 0, "error": str(exc)[:1000]}


def _heartbeat_loop(job_id: str, generation: int, stop_event: threading.Event, lease_lost: threading.Event) -> None:
    interval = max(1.0, _lease_seconds() / 3)
    while not stop_event.wait(interval):
        try:
            if not heartbeat(job_id, generation):
                lease_lost.set()
                return
        except Exception:
            lease_lost.set()
            return


def drain_job(job_id: str, generation: int, config: dict[str, Any]) -> None:
    if not config.get("auto_drain"):
        return
    while running:
        assert_lease(job_id, generation, mutation=True)
        row = _claim_any_live(job_id, generation, "DELETING")
        if not row:
            return
        add_result(job_id, generation, _delete(job_id, generation, config, row))


def run_job(job: dict[str, Any]) -> None:
    config = job["config"]
    job_id = str(job["id"])
    generation = int(job["lease_generation"])
    limit = config.get("object_limit")
    duration = config.get("duration_seconds")
    concurrency = int(config.get("concurrency", 1))
    rps = float(config.get("requests_per_second", 1))
    heartbeat_stop, lease_lost = threading.Event(), threading.Event()
    heartbeater = threading.Thread(target=_heartbeat_loop, args=(job_id, generation, heartbeat_stop, lease_lost), daemon=True)
    heartbeater.start()
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            while running and not lease_lost.is_set():
                state = state_of(job_id, generation)
                if state == "paused":
                    time.sleep(0.25)
                    continue
                if state == "stopping":
                    set_state(job_id, generation, "stopped")
                    return
                if state != "running":
                    return
                with connection() as conn:
                    current = conn.execute("SELECT sent_count,failed_count,started_at FROM stream_jobs WHERE id=%s", (job_id,)).fetchone()
                completed = int(current["sent_count"]) + int(current["failed_count"])
                elapsed = (datetime.now(timezone.utc) - current["started_at"]).total_seconds()
                remaining = concurrency if limit is None else min(concurrency, max(0, int(limit) - completed))
                if remaining <= 0 or (duration is not None and elapsed >= float(duration)):
                    if job.get("job_type") == "rgw_crud" and config.get("auto_drain"):
                        try:
                            drain_job(job_id, generation, config)
                        except CapacityRejected as exc:
                            set_state(job_id, generation, "paused", str(exc)[:1000], exc.decision.state)
                            return
                    set_state(job_id, generation, "completed")
                    return
                batch_started = time.monotonic()
                fn = perform_crud if job.get("job_type") == "rgw_crud" else put_one_legacy
                futures = [executor.submit(fn, job_id, generation, config) for _ in range(remaining)]
                for future in as_completed(futures):
                    try:
                        add_result(job_id, generation, future.result())
                    except LeaseLost:
                        lease_lost.set()
                        return
                    except Exception as exc:
                        set_state(
                            job_id,
                            generation,
                            "paused",
                            str(exc)[:1000],
                            "RECONCILE_REQUIRED_AFTER_AMBIGUOUS_MUTATION",
                        )
                        return
                target_seconds = remaining / rps
                time.sleep(max(0, target_seconds - (time.monotonic() - batch_started)))
    except LeaseLost:
        return
    except Exception as exc:
        set_state(job_id, generation, "failed", str(exc)[:1000])
    finally:
        heartbeat_stop.set()
        heartbeater.join(timeout=2)


def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    initialize()
    try:
        while running:
            job = get_job()
            if job:
                run_job(job)
            else:
                time.sleep(1)
    finally:
        pool.close()


if __name__ == "__main__":
    main()
