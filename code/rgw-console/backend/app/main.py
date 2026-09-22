import asyncio
import base64
import hashlib
import json
import mimetypes
import tempfile
import time
import uuid
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from botocore.exceptions import ClientError
from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .api.capacity import router as capacity_router
from .api.control import router as control_router
from .config import get_settings
from .corpus import CATEGORY_ALIASES, choose_random, classify, describe, resolve_corpus_path
from .db import connection, initialize, json_ready, pool, record_operation
from .models.domain import IdempotencyClaimRequest, IdempotencyDisposition, IdempotencyState
from .services.capacity_guard import CapacityRejected, finish_reservation, require_admission, require_cleanup_admission, reservation_lease
from .services.idempotency import IdempotencyError, IdempotencyService, canonical_request_fingerprint
from .services.scope_validator import InvalidScopeError, ScopeValidator
from .storage import client as s3_client
from .storage import delete_exact, exact_put, list_object_versions, object_key, replace_metadata, upload_file, upload_stream


class CorpusSelection(BaseModel):
    corpus_id: Literal["mixed", "size"]
    paths: list[str] = Field(min_length=1, max_length=1000)
    client_id: str = Field(min_length=1, max_length=100)
    bucket: str
    prefix: str = ""
    mode: Literal["single", "batch", "folder"] = "batch"


class RandomUpload(BaseModel):
    corpus_ids: list[Literal["mixed", "size"]] = Field(default_factory=lambda: ["mixed", "size"])
    client_id: str = Field(min_length=1, max_length=100)
    bucket: str
    prefix: str = ""
    category: str | None = None
    extension: str | None = None
    min_bytes: int | None = Field(default=None, ge=0)
    max_bytes: int | None = Field(default=None, ge=0)


class StreamJobCreate(BaseModel):
    schema_version: Literal[2] = 2
    job_type: Literal["legacy_put", "rgw_crud"] = "rgw_crud"
    client_id: str = Field(min_length=1, max_length=100)
    bucket: str
    prefix: str = ""
    corpus_ids: list[Literal["mixed", "size"]] = Field(default_factory=lambda: ["mixed"])
    weights: dict[str, float] = Field(default_factory=lambda: {"images": 35, "data": 25, "documents": 20, "media": 10, "archives": 10})
    requests_per_second: float = Field(default=1, gt=0, le=1000)
    concurrency: int = Field(default=1, ge=1, le=64)
    duration_seconds: int | None = Field(default=60, ge=1, le=86400)
    object_limit: int | None = Field(default=100, ge=1)
    naming_strategy: Literal["generated", "preserve"] = "generated"
    operation_weights: dict[str, float] = Field(default_factory=lambda: {
        "PUT": 28,
        "GET": 28,
        "HEAD": 3,
        "LIST": 2,
        "UPDATE": 20,
        "DELETE": 19,
    })
    max_live_objects: int = Field(default=10_000, ge=1)
    max_live_logical_bytes: int = Field(default=10 * 1024 * 1024 * 1024, ge=1)
    delete_scope: Literal["job_owned"] = "job_owned"
    auto_drain: bool = True
    version_policy: Literal["detect"] = "detect"


class MetadataUpdate(BaseModel):
    bucket: str
    key: str
    metadata: dict[str, str] = Field(default_factory=dict)
    content_type: str | None = None
    version_id: str | None = None


class DeleteTarget(BaseModel):
    key: str
    version_id: str | None = None


class BulkDeleteRequest(BaseModel):
    bucket: str
    objects: list[DeleteTarget] = Field(min_length=1, max_length=1000)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    yield
    pool.close()


app = FastAPI(title="RGW Object Lab API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(capacity_router)
app.include_router(control_router)
scope_validator = ScopeValidator()
idempotency_service = IdempotencyService()


@app.middleware("http")
async def request_identity(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID")
    try:
        request.state.request_id = str(uuid.UUID(supplied)) if supplied else str(uuid.uuid4())
    except ValueError:
        request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(InvalidScopeError)
async def invalid_scope_handler(request: Request, exc: InvalidScopeError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                "request_id": request.state.request_id,
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
                "observed_state": exc.observed_state,
            }
        },
    )


@app.exception_handler(IdempotencyError)
async def idempotency_error_handler(request: Request, exc: IdempotencyError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                "request_id": request.state.request_id,
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
                "observed_state": exc.observed_state,
            }
        },
    )


@app.exception_handler(CapacityRejected)
async def capacity_rejected_handler(request: Request, exc: CapacityRejected):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                "request_id": request.state.request_id,
                "code": exc.code,
                "message": str(exc),
                "retryable": exc.decision.retryable,
                "observed_state": exc.decision.to_dict(),
            }
        },
    )


def friendly_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ClientError):
        detail = exc.response.get("Error", {}).get("Message", str(exc))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 502)
        return HTTPException(status if 400 <= status < 600 else 502, detail)
    return HTTPException(502, str(exc))


def begin_idempotent_mutation(
    request: Request,
    *,
    idempotency_key: str,
    scope: str,
    method: str,
    resource: str,
    payload: object,
    content_sha256: str | None = None,
):
    fingerprint = canonical_request_fingerprint(
        method,
        resource,
        payload,
        content_sha256=content_sha256,
    )
    result = idempotency_service.claim(
        IdempotencyClaimRequest(
            scope=scope,
            idempotency_key=idempotency_key,
            http_method=method,
            resource=resource,
            request_fingerprint=fingerprint,
            owner_id=request.state.request_id,
            request_id=uuid.UUID(request.state.request_id),
        )
    )
    if result.disposition is IdempotencyDisposition.REPLAY:
        return result, JSONResponse(
            status_code=result.record.response_status or 200,
            content=result.record.response_body or {},
            headers={"Idempotency-Replayed": "true"},
        )
    if result.disposition is IdempotencyDisposition.IN_PROGRESS:
        raise HTTPException(
            409,
            {
                "request_id": str(result.record.request_id),
                "code": "IDEMPOTENCY_IN_PROGRESS",
                "message": "The same mutation is already in progress",
                "retryable": True,
                "observed_state": {"state": result.record.state.value},
            },
        )
    return result, None


def mark_idempotent_mutation_started(claim):
    record = idempotency_service.mark_in_progress(
        claim.record.scope,
        claim.record.idempotency_key,
        owner_id=claim.record.owner_id,
        fencing_generation=claim.record.fencing_generation,
    )
    claim.record = record
    return claim


def finish_idempotent_mutation(claim, body: dict, status: int = 200):
    idempotency_service.finish(
        claim.record.scope,
        claim.record.idempotency_key,
        owner_id=claim.record.owner_id,
        fencing_generation=claim.record.fencing_generation,
        state=IdempotencyState.SUCCEEDED,
        response_status=status,
        response_body=body,
    )


def fail_idempotent_mutation(
    claim,
    exc: Exception,
    *,
    retryable: bool = True,
    error_code: str = "RGW_MUTATION_FAILED",
    response_status: int = 502,
):
    idempotency_service.finish(
        claim.record.scope,
        claim.record.idempotency_key,
        owner_id=claim.record.owner_id,
        fencing_generation=claim.record.fencing_generation,
        state=IdempotencyState.FAILED_RETRYABLE if retryable else IdempotencyState.FAILED_FINAL,
        response_status=response_status,
        response_body={
            "detail": {
                "request_id": str(claim.record.request_id),
                "code": error_code,
                "message": str(exc)[:1000],
                "retryable": retryable,
                "observed_state": None,
            }
        },
        error_code=error_code,
    )


@app.get("/api/health")
def health():
    try:
        response = s3_client().list_buckets()
        visible = [row for row in response.get("Buckets", []) if row.get("Name") in scope_validator.allowed_buckets]
        with connection() as conn:
            revision = conn.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        return {
            "status": "ok",
            "endpoint": get_settings().rgw_endpoint_url,
            "buckets": len(visible),
            "bucket_scope": "CURRENT_S3_IDENTITY",
            "schema_version": revision["version"] if revision else None,
        }
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "degraded", "endpoint": get_settings().rgw_endpoint_url, "error": str(exc)})


@app.get("/api/buckets")
def buckets():
    try:
        return [
            {"name": row["Name"], "created_at": row.get("CreationDate"), "scope": "CURRENT_S3_IDENTITY"}
            for row in s3_client().list_buckets().get("Buckets", [])
            if row.get("Name") in scope_validator.allowed_buckets
        ]
    except Exception as exc:
        raise friendly_error(exc)


@app.get("/api/corpora")
def corpora():
    answer = []
    for corpus_id, root in get_settings().corpus_roots.items():
        exists = root.is_dir()
        files = [path for path in root.rglob("*") if path.is_file()] if exists else []
        answer.append({"id": corpus_id, "label": "Mixed-file corpus" if corpus_id == "mixed" else "Size corpus", "available": exists, "file_count": len(files), "total_bytes": sum(path.stat().st_size for path in files)})
    return answer


@app.get("/api/corpora/{corpus_id}/browse")
def browse_corpus(corpus_id: str, path: str = ""):
    root, current = resolve_corpus_path(corpus_id, path)
    if not current.is_dir():
        raise HTTPException(400, "Browse path must be a directory")
    items = sorted((describe(item, root) for item in current.iterdir()), key=lambda row: (row["kind"] != "directory", row["name"].lower()))
    parent = current.parent.relative_to(root).as_posix() if current != root else None
    if parent == ".":
        parent = ""
    return {"corpus_id": corpus_id, "path": path, "parent": parent, "items": items}


@app.post("/api/uploads/corpus")
def upload_corpus(
    selection: CorpusSelection,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
):
    scope_validator.require_bucket(selection.bucket)
    root, _ = resolve_corpus_path(selection.corpus_id)
    resource = f"rgw://{selection.bucket}/corpus-upload"
    claim, replay = begin_idempotent_mutation(
        request,
        idempotency_key=idempotency_key,
        scope=resource,
        method="POST",
        resource=resource,
        payload=selection,
    )
    if replay:
        return replay
    results = []
    mutation_started = False
    for relative in selection.paths:
        decision = None
        try:
            _, selected = resolve_corpus_path(selection.corpus_id, relative)
            paths = [selected] if selected.is_file() else [path for path in selected.rglob("*") if path.is_file()]
            for path in paths:
                decision = None
                category = classify(path)
                # A folder upload keeps the selected folder name and every child
                # directory beneath it; single/batch uploads use only the key schema.
                relative_base = selected.parent if selection.mode == "folder" and selected.is_dir() else path.parent
                parent = path.relative_to(relative_base).parent.as_posix()
                parent = "" if parent == "." else parent
                key = object_key(selection.client_id, selection.mode, category, path.name, selection.prefix, parent)
                scope_validator.require_key(selection.bucket, key)
                decision = require_admission("PUT", path.stat().st_size, request_id=request.state.request_id)
                with reservation_lease(decision):
                    if not mutation_started:
                        mark_idempotent_mutation_started(claim)
                        mutation_started = True
                    uploaded = upload_file(path, selection.bucket, key, selection.client_id, category, "web", request_id=request.state.request_id, capacity_decision_id=decision.id)
                finish_reservation(decision, "success")
                results.append(uploaded)
        except Exception as exc:
            if decision is not None:
                try:
                    finish_reservation(decision, "ambiguous")
                except Exception:
                    pass
            results.append({"success": False, "path": relative, "error": str(exc)})
    body = {"results": results, "succeeded": sum(item["success"] for item in results), "failed": sum(not item["success"] for item in results)}
    finish_idempotent_mutation(claim, body)
    return body


@app.post("/api/uploads/random")
def upload_random(
    upload_request: RandomUpload,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
):
    scope_validator.require_bucket(upload_request.bucket)
    resource = f"rgw://{upload_request.bucket}/random-upload"
    claim, replay = begin_idempotent_mutation(
        request,
        idempotency_key=idempotency_key,
        scope=resource,
        method="POST",
        resource=resource,
        payload=upload_request,
    )
    if replay:
        return replay
    try:
        corpus_id, root, path = choose_random(upload_request.corpus_ids, upload_request.category, upload_request.extension, upload_request.min_bytes, upload_request.max_bytes)
        category = classify(path)
        key = object_key(upload_request.client_id, "random", category, path.name, upload_request.prefix)
        scope_validator.require_key(upload_request.bucket, key)
        decision = require_admission("PUT", path.stat().st_size, request_id=request.state.request_id)
        with reservation_lease(decision):
            mark_idempotent_mutation_started(claim)
            result = upload_file(path, upload_request.bucket, key, upload_request.client_id, category, "web", request_id=request.state.request_id, capacity_decision_id=decision.id)
        finish_reservation(decision, "success")
        result.update({"corpus_id": corpus_id, "corpus_path": path.relative_to(root).as_posix()})
        finish_idempotent_mutation(claim, result)
        return result
    except HTTPException:
        raise
    except CapacityRejected as exc:
        fail_idempotent_mutation(claim, exc, error_code="CAPACITY_RETRYABLE", response_status=exc.status_code)
        raise
    except InvalidScopeError as exc:
        fail_idempotent_mutation(claim, exc, retryable=False, error_code="INVALID_SCOPE", response_status=exc.status_code)
        raise
    except Exception as exc:
        if "decision" in locals():
            try:
                finish_reservation(decision, "ambiguous")
            except Exception:
                pass
        fail_idempotent_mutation(claim, exc, retryable=False, error_code="AMBIGUOUS_EXTERNAL_RESULT")
        raise friendly_error(exc)


@app.post("/api/uploads/browser")
def upload_browser(
    request: Request,
    file: Annotated[UploadFile, File()], client_id: Annotated[str, Form()], bucket: Annotated[str, Form()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    prefix: Annotated[str, Form()] = "", mode: Annotated[str, Form()] = "single", relative_path: Annotated[str, Form()] = "",
):
    filename = Path(file.filename or "unnamed").name
    category = classify(Path(filename))
    relative_parent = PurePosixPath(relative_path).parent.as_posix() if relative_path else ""
    if relative_parent == ".":
        relative_parent = ""
    key = object_key(client_id, mode, category, filename, prefix, relative_parent)
    try:
        scope_validator.require_key(bucket, key)
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        digest = hashlib.sha256()
        while chunk := file.file.read(1024 * 1024):
            digest.update(chunk)
        file.file.seek(0)
        resource = f"rgw://{bucket}/browser-upload"
        claim, replay = begin_idempotent_mutation(
            request,
            idempotency_key=idempotency_key,
            scope=resource,
            method="POST",
            resource=resource,
            payload={
                "client_id": client_id,
                "prefix": prefix,
                "mode": mode,
                "relative_path": relative_path,
                "filename": filename,
                "content_type": file.content_type,
                "size": size,
            },
            content_sha256=digest.hexdigest(),
        )
        if replay:
            return replay
        decision = require_admission("PUT", size, request_id=request.state.request_id)
        mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with reservation_lease(decision):
            mark_idempotent_mutation_started(claim)
            result = upload_stream(file.file, size, filename, bucket, key, client_id, category, "web", mime, request_id=request.state.request_id, capacity_decision_id=decision.id)
        finish_reservation(decision, "success")
        finish_idempotent_mutation(claim, result)
        return result
    except CapacityRejected as exc:
        if "claim" in locals():
            fail_idempotent_mutation(claim, exc, error_code="CAPACITY_RETRYABLE", response_status=exc.status_code)
        raise
    except InvalidScopeError as exc:
        if "claim" in locals():
            fail_idempotent_mutation(claim, exc, retryable=False, error_code="INVALID_SCOPE", response_status=exc.status_code)
        raise
    except Exception as exc:
        if "decision" in locals():
            try:
                finish_reservation(decision, "ambiguous")
            except Exception:
                pass
        if "claim" in locals():
            fail_idempotent_mutation(claim, exc, retryable=False, error_code="AMBIGUOUS_EXTERNAL_RESULT")
        raise friendly_error(exc)


@app.get("/api/objects")
def list_objects(
    bucket: str, prefix: str = "", continuation_token: str | None = None, max_keys: int = Query(100, ge=1, le=1000),
    client_id: str | None = None, category: str | None = None, name: str | None = None,
    min_bytes: int | None = None, max_bytes: int | None = None,
    start_time: datetime | None = None, end_time: datetime | None = None,
):
    scope_validator.require_prefix(bucket, prefix, streaming=False)
    effective_prefix = prefix.strip("/")
    if client_id and not effective_prefix:
        effective_prefix = f"clients/{client_id}/"
    params = {"Bucket": bucket, "Prefix": effective_prefix, "MaxKeys": max_keys}
    if continuation_token:
        params["ContinuationToken"] = continuation_token
    started = time.perf_counter()
    try:
        response = s3_client().list_objects_v2(**params)
    except Exception as exc:
        record_operation(kind="LIST", success=False, bytes_count=0, latency_ms=(time.perf_counter() - started) * 1000, bucket=bucket, object_key=effective_prefix or "*", client_id=client_id, category=category, source="web", content_type=None, error=str(exc)[:1000], error_code="RGW_LIST_FAILED")
        raise friendly_error(exc)
    objects = []
    for item in response.get("Contents", []):
        key = item["Key"]
        parts = key.split("/")
        try:
            clients_index = parts.index("clients")
        except ValueError:
            clients_index = -1
        parsed_client = parts[clients_index + 1] if clients_index >= 0 and len(parts) > clients_index + 3 else None
        parsed_category = parts[clients_index + 3] if clients_index >= 0 and len(parts) > clients_index + 3 else None
        if client_id and parsed_client != client_id:
            continue
        if category and parsed_category != CATEGORY_ALIASES.get(category, category):
            continue
        if name and name.lower() not in key.lower():
            continue
        if min_bytes is not None and item["Size"] < min_bytes:
            continue
        if max_bytes is not None and item["Size"] > max_bytes:
            continue
        modified = item["LastModified"]
        if start_time and modified < start_time:
            continue
        if end_time and modified > end_time:
            continue
        mime = mimetypes.guess_type(key)[0] or "application/octet-stream"
        objects.append({"key": key, "client_id": parsed_client, "category": parsed_category, "extension": PurePosixPath(key).suffix.lower().lstrip("."), "content_type": mime, "size": item["Size"], "last_modified": item["LastModified"], "etag": item["ETag"].strip('"'), "bucket": bucket, "prefix": str(PurePosixPath(key).parent), "source": "external"})
    if objects:
        keys = [row["key"] for row in objects]
        with connection() as conn:
            rows = conn.execute("SELECT DISTINCT ON (object_key) object_key, source FROM operations WHERE bucket=%s AND object_key=ANY(%s) ORDER BY object_key, created_at DESC", (bucket, keys)).fetchall()
        source_by_key = {row["object_key"]: row["source"] for row in rows}
        for row in objects:
            row["source"] = source_by_key.get(row["key"], "external")
    record_operation(kind="LIST", success=True, bytes_count=0, latency_ms=(time.perf_counter() - started) * 1000, bucket=bucket, object_key=effective_prefix or "*", client_id=client_id, category=category, source="web", content_type=None, error=None)
    return {"objects": objects, "is_truncated": response.get("IsTruncated", False), "next_token": response.get("NextContinuationToken")}


@app.get("/api/objects/head")
def head_object(bucket: str, key: str):
    scope_validator.require_key(bucket, key)
    started = time.perf_counter()
    try:
        response = s3_client().head_object(Bucket=bucket, Key=key)
        record_operation(kind="HEAD", success=True, bytes_count=0, latency_ms=(time.perf_counter() - started) * 1000, bucket=bucket, object_key=key, client_id=None, category=None, source="web", content_type=response.get("ContentType"), error=None)
        return {"bucket": bucket, "key": key, "version_id": response.get("VersionId"), "delete_marker": bool(response.get("DeleteMarker", False)), "size": response.get("ContentLength"), "content_type": response.get("ContentType"), "etag": response.get("ETag", "").strip('"'), "last_modified": response.get("LastModified"), "metadata": response.get("Metadata", {}), "accept_ranges": response.get("AcceptRanges", "bytes")}
    except Exception as exc:
        record_operation(kind="HEAD", success=False, bytes_count=0, latency_ms=(time.perf_counter() - started) * 1000, bucket=bucket, object_key=key, client_id=None, category=None, source="web", content_type=None, error=str(exc)[:1000], error_code="RGW_HEAD_FAILED")
        raise friendly_error(exc)


@app.get("/api/objects/content")
def get_object(bucket: str, key: str, download: bool = False, range_header: Annotated[str | None, Header(alias="Range")] = None):
    scope_validator.require_key(bucket, key)
    params = {"Bucket": bucket, "Key": key}
    if range_header:
        params["Range"] = range_header
    started = time.perf_counter()
    try:
        response = s3_client().get_object(**params)
    except Exception as exc:
        raise friendly_error(exc)
    headers = {"Accept-Ranges": "bytes", "ETag": response.get("ETag", ""), "Content-Length": str(response.get("ContentLength", 0))}
    if response.get("ContentRange"):
        headers["Content-Range"] = response["ContentRange"]
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{Path(key).name}"'

    def chunks():
        sent = 0
        ok = True
        error = None
        try:
            for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024):
                if chunk:
                    sent += len(chunk)
                    yield chunk
        except Exception as exc:
            ok, error = False, str(exc)
            raise
        finally:
            record_operation(kind="GET", success=ok, bytes_count=sent, latency_ms=(time.perf_counter() - started) * 1000, bucket=bucket, object_key=key, client_id=None, category=None, source="web", content_type=response.get("ContentType"), error=error)

    status = 206 if response.get("ContentRange") else 200
    return StreamingResponse(chunks(), status_code=status, media_type=response.get("ContentType", "application/octet-stream"), headers=headers)


@app.put("/api/objects/content")
async def put_object_content(
    request: Request,
    bucket: str,
    key: str,
    content_length: Annotated[int, Header(alias="Content-Length", ge=0)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    content_type: Annotated[str, Header(alias="Content-Type")] = "application/octet-stream",
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    scope_validator.require_key(bucket, key)
    max_bytes = 5 * 1024 * 1024 * 1024
    if content_length > max_bytes:
        raise HTTPException(413, f"Object exceeds the {max_bytes}-byte bounded staging limit")
    digest = hashlib.sha256()
    received = 0
    with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b") as body:
        async for chunk in request.stream():
            received += len(chunk)
            if received > content_length or received > max_bytes:
                raise HTTPException(413, "Request body exceeded declared Content-Length")
            digest.update(chunk)
            await asyncio.to_thread(body.write, chunk)
        if received != content_length:
            raise HTTPException(400, f"Content-Length declared {content_length} bytes but received {received}")
        body.seek(0)
        resource = f"rgw://{bucket}/{key}"
        claim, replay = await asyncio.to_thread(
            partial(
                begin_idempotent_mutation,
                request,
                idempotency_key=idempotency_key,
                scope=resource,
                method="PUT",
                resource=resource,
                payload={"content_length": content_length, "content_type": content_type, "if_match": if_match},
                content_sha256=digest.hexdigest(),
            )
        )
        if replay:
            return replay
        try:
            decision = await asyncio.to_thread(require_admission, "UPDATE", content_length, request_id=request.state.request_id)
            def execute_put():
                with reservation_lease(decision):
                    mark_idempotent_mutation_started(claim)
                    return exact_put(
                        body, content_length, bucket, key,
                        content_type=content_type,
                        metadata={"sha256": digest.hexdigest(), "source": "web-exact"},
                        request_id=request.state.request_id,
                        capacity_decision_id=decision.id,
                        if_match=if_match,
                    )
            result = await asyncio.to_thread(execute_put)
            await asyncio.to_thread(finish_reservation, decision, "success")
            result.update({"request_id": request.state.request_id, "capacity_decision": decision.to_dict()})
            await asyncio.to_thread(finish_idempotent_mutation, claim, result)
            return result
        except Exception as exc:
            if "decision" in locals() and not isinstance(exc, CapacityRejected):
                try:
                    await asyncio.to_thread(finish_reservation, decision, "ambiguous")
                except Exception:
                    pass
            await asyncio.to_thread(
                partial(
                    fail_idempotent_mutation,
                    claim,
                    exc,
                    retryable=isinstance(exc, CapacityRejected),
                    error_code="CAPACITY_RETRYABLE" if isinstance(exc, CapacityRejected) else "AMBIGUOUS_EXTERNAL_RESULT",
                )
            )
            if isinstance(exc, CapacityRejected):
                raise
            raise friendly_error(exc)


@app.patch("/api/objects/metadata")
def update_object_metadata(
    update: MetadataUpdate,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
):
    scope_validator.require_key(update.bucket, update.key)
    resource = f"rgw://{update.bucket}/{update.key}"
    claim, replay = begin_idempotent_mutation(
        request,
        idempotency_key=idempotency_key,
        scope=resource,
        method="PATCH",
        resource=f"{resource}/metadata",
        payload=update,
    )
    if replay:
        return replay
    try:
        params = {"Bucket": update.bucket, "Key": update.key}
        if update.version_id:
            params["VersionId"] = update.version_id
        head = s3_client().head_object(**params)
        decision = require_admission(
            "UPDATE",
            int(head.get("ContentLength") or 0),
            request_id=request.state.request_id,
        )
        with reservation_lease(decision):
            mark_idempotent_mutation_started(claim)
            result = replace_metadata(
                update.bucket,
                update.key,
                update.metadata,
                content_type=update.content_type,
                version_id=update.version_id,
                request_id=request.state.request_id,
                capacity_decision_id=decision.id,
            )
        finish_reservation(decision, "success")
        result.update({"request_id": request.state.request_id, "capacity_decision": decision.to_dict()})
        finish_idempotent_mutation(claim, result)
        return result
    except CapacityRejected as exc:
        fail_idempotent_mutation(claim, exc, error_code="CAPACITY_RETRYABLE")
        raise
    except Exception as exc:
        if "decision" in locals():
            try:
                finish_reservation(decision, "ambiguous")
            except Exception:
                pass
        fail_idempotent_mutation(claim, exc, retryable=False, error_code="AMBIGUOUS_EXTERNAL_RESULT")
        raise friendly_error(exc)


@app.delete("/api/objects")
def delete_object(
    request: Request,
    bucket: str,
    key: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    version_id: str | None = None,
):
    scope_validator.require_key(bucket, key)
    resource = f"rgw://{bucket}/{key}"
    claim, replay = begin_idempotent_mutation(
        request,
        idempotency_key=idempotency_key,
        scope=resource,
        method="DELETE",
        resource=resource,
        payload={"version_id": version_id},
    )
    if replay:
        return replay
    try:
        versioning = s3_client().get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")
        capacity = None
        if versioning in {"Enabled", "Suspended"} and not version_id:
            capacity = require_admission("UPDATE", 1, request_id=request.state.request_id)
        else:
            capacity = require_cleanup_admission(request_id=request.state.request_id)
        with reservation_lease(capacity):
            mark_idempotent_mutation_started(claim)
            result = delete_exact(bucket, key, version_id=version_id, request_id=request.state.request_id)
        finish_reservation(capacity, "success")
        result["hard_delete"] = bool(version_id) or versioning == "Disabled"
        result["delete_semantics"] = "HARD_DELETE" if result["hard_delete"] else "DELETE_MARKER_POSSIBLE"
        result.update(
            {
                "request_id": request.state.request_id,
                "bucket_versioning": versioning,
                "capacity_decision": capacity.to_dict() if capacity else None,
                "capacity_release": "AWAITING_TELEMETRY",
            }
        )
        finish_idempotent_mutation(claim, result)
        return result
    except CapacityRejected as exc:
        fail_idempotent_mutation(claim, exc, error_code="CAPACITY_RETRYABLE")
        raise
    except Exception as exc:
        if "capacity" in locals() and capacity is not None:
            try:
                finish_reservation(capacity, "ambiguous")
            except Exception:
                pass
        fail_idempotent_mutation(claim, exc, retryable=False, error_code="AMBIGUOUS_EXTERNAL_RESULT")
        raise friendly_error(exc)


@app.post("/api/objects/bulk-delete")
def bulk_delete_objects(
    deletion: BulkDeleteRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
):
    scope_validator.require_bucket(deletion.bucket)
    for item in deletion.objects:
        scope_validator.require_key(deletion.bucket, item.key)
    resource = f"rgw://{deletion.bucket}/bulk-delete"
    claim, replay = begin_idempotent_mutation(
        request,
        idempotency_key=idempotency_key,
        scope=resource,
        method="POST",
        resource=resource,
        payload=deletion,
    )
    if replay:
        return replay
    try:
        versioning = s3_client().get_bucket_versioning(Bucket=deletion.bucket).get("Status", "Disabled")
        capacity = None
        capacity_decisions = []
        marker_count = sum(item.version_id is None for item in deletion.objects)
        cleanup_count = sum(item.version_id is not None for item in deletion.objects)
        if versioning == "Disabled":
            cleanup_count = len(deletion.objects)
        if versioning in {"Enabled", "Suspended"} and marker_count:
            capacity = require_admission("UPDATE", marker_count, request_id=request.state.request_id, object_count=marker_count)
            capacity_decisions.append(capacity)
        if cleanup_count:
            cleanup_decision = require_cleanup_admission(request_id=request.state.request_id, object_count=cleanup_count)
            capacity_decisions.append(cleanup_decision)
            capacity = capacity or cleanup_decision
    except CapacityRejected as exc:
        fail_idempotent_mutation(claim, exc, error_code="CAPACITY_RETRYABLE")
        raise
    except Exception as exc:
        fail_idempotent_mutation(claim, exc, error_code="RGW_PREFLIGHT_FAILED")
        raise friendly_error(exc)
    results = []
    try:
        with ExitStack() as reservation_stack:
            for decision in capacity_decisions:
                reservation_stack.enter_context(reservation_lease(decision))
            mark_idempotent_mutation_started(claim)
            for item in deletion.objects:
                try:
                    result = delete_exact(deletion.bucket, item.key, version_id=item.version_id, request_id=request.state.request_id)
                    result["hard_delete"] = bool(item.version_id) or versioning == "Disabled"
                    result["delete_semantics"] = "HARD_DELETE" if result["hard_delete"] else "DELETE_MARKER_POSSIBLE"
                    results.append(result)
                except Exception as exc:
                    results.append({"success": False, "key": item.key, "version_id": item.version_id, "error": str(exc)[:1000]})
    except Exception as exc:
        for decision in capacity_decisions:
            try:
                finish_reservation(decision, "ambiguous")
            except Exception:
                pass
        fail_idempotent_mutation(claim, exc, retryable=False, error_code="AMBIGUOUS_EXTERNAL_RESULT")
        raise friendly_error(exc)
    body = {
        "request_id": request.state.request_id,
        "results": results,
        "succeeded": sum(bool(row.get("success")) for row in results),
        "failed": sum(not bool(row.get("success")) for row in results),
        "bucket_versioning": versioning,
        "capacity_decision": capacity.to_dict() if capacity else None,
        "capacity_release": "AWAITING_TELEMETRY",
    }
    reservation_outcome = "success" if not body["failed"] else "ambiguous"
    for decision in capacity_decisions:
        finish_reservation(decision, reservation_outcome)
    status = 207 if body["failed"] else 200
    finish_idempotent_mutation(claim, body, status)
    return JSONResponse(status_code=status, content=body)


def _decode_version_token(token: str | None) -> tuple[str | None, str | None]:
    if not token:
        return None, None
    try:
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        return data.get("key_marker"), data.get("version_id_marker")
    except Exception as exc:
        raise HTTPException(400, "Invalid versions continuation token") from exc


def _encode_version_token(key_marker: str | None, version_id_marker: str | None) -> str | None:
    if not key_marker:
        return None
    raw = json.dumps({"key_marker": key_marker, "version_id_marker": version_id_marker}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@app.get("/api/objects/versions")
def object_versions(
    bucket: str,
    prefix: str = "",
    key: str | None = None,
    continuation_token: str | None = None,
    max_keys: int = Query(100, ge=1, le=1000),
):
    if key:
        scope_validator.require_key(bucket, key)
        effective_prefix = key
    else:
        scope_validator.require_prefix(bucket, prefix)
        effective_prefix = prefix
    key_marker, version_marker = _decode_version_token(continuation_token)
    try:
        result = list_object_versions(
            bucket,
            prefix=effective_prefix,
            key_marker=key_marker,
            version_id_marker=version_marker,
            max_keys=max_keys,
        )
        if key:
            result["versions"] = [row for row in result["versions"] if row.get("key") == key]
        result["next_token"] = _encode_version_token(result.pop("next_key_marker"), result.pop("next_version_id_marker"))
        result["bucket_versioning"] = s3_client().get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise friendly_error(exc)


@app.post("/api/jobs", status_code=201)
def create_job(config: StreamJobCreate):
    scope_validator.require_bucket(config.bucket)
    scope_prefix = scope_validator.build_stream_prefix(config.prefix)
    job_id = str(uuid.uuid4())
    payload = config.model_dump(mode="json")
    payload["scope_prefix"] = scope_prefix
    payload["stream_root"] = scope_validator.stream_prefix_root
    with connection() as conn:
        row = conn.execute(
            "INSERT INTO stream_jobs (id, state, job_type, config) VALUES (%s, 'pending', %s, %s::jsonb) RETURNING *",
            (job_id, config.job_type, json.dumps(payload)),
        ).fetchone()
        conn.commit()
    return json_ready(row)


@app.get("/api/jobs")
def jobs():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM stream_jobs ORDER BY created_at DESC LIMIT 100").fetchall()
    return [json_ready(row) for row in rows]


@app.post("/api/jobs/{job_id}/{action}")
def control_job(job_id: str, action: Literal["pause", "resume", "stop"]):
    with connection() as conn:
        if action == "resume":
            control = conn.execute("SELECT desired_state,reason FROM control_state WHERE id=true").fetchone()
            if control["desired_state"] == "READ_CLEANUP_ONLY":
                raise HTTPException(409, {"code": "READ_CLEANUP_ONLY", "message": control["reason"], "retryable": True})
        if action == "pause":
            row = conn.execute(
                "UPDATE stream_jobs SET state='paused', paused_reason='OPERATOR_PAUSE', updated_at=now() WHERE id=%s AND state IN ('pending','running') RETURNING *",
                (job_id,),
            ).fetchone()
        elif action == "resume":
            row = conn.execute(
                """
                UPDATE stream_jobs
                   SET state=CASE WHEN lease_expires_at > now() THEN 'running' ELSE 'pending' END,
                       lease_owner=CASE WHEN lease_expires_at > now() THEN lease_owner ELSE NULL END,
                       lease_expires_at=CASE WHEN lease_expires_at > now() THEN lease_expires_at ELSE NULL END,
                       paused_reason=NULL, updated_at=now()
                 WHERE id=%s AND state='paused'
                   AND coalesce(paused_reason,'') NOT IN (
                     'RECONCILE_REQUIRED_AFTER_AMBIGUOUS_MUTATION',
                     'LEASE_EXPIRED_RECONCILE_REQUIRED'
                   )
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                UPDATE stream_jobs
                   SET state=CASE
                         WHEN state='pending' THEN 'stopped'
                         WHEN state='paused' AND (lease_expires_at IS NULL OR lease_expires_at <= now()) THEN 'stopped'
                         ELSE 'stopping'
                       END,
                       paused_reason=CASE
                         WHEN state='paused' AND (lease_expires_at IS NULL OR lease_expires_at <= now())
                           THEN 'STOPPED_AFTER_EXPIRED_LEASE_RECONCILE_CATALOG'
                         ELSE paused_reason
                       END,
                       finished_at=CASE
                         WHEN state='pending' OR (state='paused' AND (lease_expires_at IS NULL OR lease_expires_at <= now()))
                           THEN now()
                         ELSE finished_at
                       END,
                       updated_at=now()
                 WHERE id=%s AND state IN ('pending','running','paused','stopping')
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "Active job not found")
    return json_ready(row)


def metrics_snapshot() -> dict:
    with connection() as conn:
        summary = conn.execute("""SELECT count(*) FILTER (WHERE kind='PUT') AS puts, count(*) FILTER (WHERE kind='GET') AS gets,
          count(*) FILTER (WHERE kind='HEAD') AS heads, count(*) FILTER (WHERE kind='LIST') AS lists,
          count(*) FILTER (WHERE kind='UPDATE') AS updates, count(*) FILTER (WHERE kind='DELETE') AS deletes,
          count(*) FILTER (WHERE success) AS success, count(*) FILTER (WHERE NOT success) AS failure,
          coalesce(sum(bytes_count) FILTER (WHERE kind IN ('PUT','UPDATE')),0) AS bytes_sent, coalesce(sum(bytes_count) FILTER (WHERE kind='GET'),0) AS bytes_received,
          coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms),0) AS p50,
          coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),0) AS p95,
          coalesce(percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms),0) AS p99,
          coalesce(max(latency_ms) FILTER (WHERE created_at=(SELECT max(created_at) FROM operations)),0) AS latest_latency
          FROM operations""").fetchone()
        recent = conn.execute("SELECT object_key, kind, success, latency_ms, bytes_count, created_at FROM operations ORDER BY created_at DESC LIMIT 8").fetchall()
        window = conn.execute("SELECT count(*) AS objects, coalesce(sum(bytes_count),0) AS bytes FROM operations WHERE created_at > now() - interval '10 seconds'").fetchone()
        active = conn.execute("SELECT count(*) AS count FROM stream_jobs WHERE state IN ('pending','running','paused','stopping')").fetchone()["count"]
    result = dict(summary)
    result.update({"objects_per_second": float(window["objects"]) / 10, "mib_per_second": float(window["bytes"]) / 10 / 1048576, "active_jobs": active, "recent": [json_ready(row) for row in recent]})
    return result


@app.get("/api/metrics")
def metrics():
    return metrics_snapshot()


@app.get("/api/metrics/stream")
async def metric_stream():
    async def events():
        while True:
            try:
                snapshot = await asyncio.to_thread(metrics_snapshot)
                yield f"data: {json.dumps(snapshot, default=str)}\n\n"
            except asyncio.CancelledError:
                break
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
