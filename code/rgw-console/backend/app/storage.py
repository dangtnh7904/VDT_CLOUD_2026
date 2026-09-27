import mimetypes
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

import boto3
from botocore.config import Config

from .config import get_settings
from .db import record_operation


LOGGER = logging.getLogger(__name__)


def _journal_operation(**values) -> bool:
    """Keep an audit-store outage from changing an already completed S3 result."""
    try:
        record_operation(**values)
        return True
    except Exception as exc:
        LOGGER.error("operation journal write failed after RGW result: %s", type(exc).__name__)
        return False


def client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.rgw_endpoint_url,
        aws_access_key_id=settings.rgw_access_key,
        aws_secret_access_key=settings.rgw_secret_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def clean_segment(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return cleaned[:100] or fallback


def s3_metadata(metadata: dict[str, str] | None) -> dict[str, str]:
    """Return HTTP-header-safe S3 metadata while retaining Unicode reversibly."""
    encoded: dict[str, str] = {}
    for key, raw_value in (metadata or {}).items():
        value = str(raw_value)
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            value = quote(value, safe="")
        encoded[str(key)] = value
    return encoded


def object_key(
    client_id: str,
    mode: str,
    category: str,
    original_name: str,
    prefix: str = "",
    relative_parent: str = "",
    naming_strategy: str = "generated",
    root_prefix: str = "",
) -> str:
    now = datetime.now(timezone.utc)
    original = Path(original_name)
    suffix = "".join(original.suffixes).lower()
    identity = f"{now.strftime('%H%M%S%f')[:-3]}-{uuid.uuid4().hex[:12]}"
    if naming_strategy == "preserve":
        stem = original.name[:-len(suffix)] if suffix else original.name
        unique_name = f"{identity}-{clean_segment(stem, 'object')}{suffix}"
    else:
        unique_name = f"{identity}{suffix}"
    parts = [
        root_prefix.strip("/"), "clients", clean_segment(client_id), clean_segment(mode), clean_segment(category),
        now.strftime("%Y-%m-%d"), prefix.strip("/"), relative_parent.strip("/"), unique_name,
    ]
    return "/".join(part for part in parts if part)


def upload_file(
    path: Path,
    bucket: str,
    key: str,
    client_id: str,
    category: str,
    source: str,
    content_type: str | None = None,
    *,
    request_id: str | None = None,
    job_id: str | None = None,
    capacity_decision_id: str | None = None,
) -> dict:
    size = path.stat().st_size
    mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    started = time.perf_counter()
    try:
        with path.open("rb") as body:
            response = client().put_object(
                Bucket=bucket, Key=key, Body=body, ContentType=mime,
                Metadata=s3_metadata({"client-id": clean_segment(client_id), "category": category, "source": source, "original-name": path.name}),
            )
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(kind="PUT", success=True, bytes_count=size, latency_ms=latency, bucket=bucket, object_key=key, client_id=client_id, category=category, source=source, content_type=mime, error=None, request_id=request_id, job_id=job_id, capacity_decision_id=capacity_decision_id, bytes_delta_logical=size)
        return {"success": True, "bucket": bucket, "key": key, "filename": path.name, "size": size, "content_type": mime, "etag": response.get("ETag", "").strip('"'), "latency_ms": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(kind="PUT", success=False, bytes_count=0, latency_ms=latency, bucket=bucket, object_key=key, client_id=client_id, category=category, source=source, content_type=mime, error=str(exc)[:1000], request_id=request_id, job_id=job_id, capacity_decision_id=capacity_decision_id, error_code="RGW_PUT_FAILED")
        raise


def upload_stream(
    body: BinaryIO,
    size: int,
    original_name: str,
    bucket: str,
    key: str,
    client_id: str,
    category: str,
    source: str,
    content_type: str,
    *,
    request_id: str | None = None,
    capacity_decision_id: str | None = None,
) -> dict:
    started = time.perf_counter()
    try:
        response = client().put_object(Bucket=bucket, Key=key, Body=body, ContentLength=size, ContentType=content_type,
            Metadata=s3_metadata({"client-id": clean_segment(client_id), "category": category, "source": source, "original-name": original_name}))
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(kind="PUT", success=True, bytes_count=size, latency_ms=latency, bucket=bucket, object_key=key, client_id=client_id, category=category, source=source, content_type=content_type, error=None, request_id=request_id, capacity_decision_id=capacity_decision_id, bytes_delta_logical=size)
        return {"success": True, "bucket": bucket, "key": key, "filename": original_name, "size": size, "content_type": content_type, "etag": response.get("ETag", "").strip('"'), "latency_ms": round(latency, 2)}
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(kind="PUT", success=False, bytes_count=0, latency_ms=latency, bucket=bucket, object_key=key, client_id=client_id, category=category, source=source, content_type=content_type, error=str(exc)[:1000], request_id=request_id, capacity_decision_id=capacity_decision_id, error_code="RGW_PUT_FAILED")
        raise


def exact_put(
    body: BinaryIO,
    size: int,
    bucket: str,
    key: str,
    *,
    content_type: str,
    metadata: dict[str, str] | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    capacity_decision_id: str | None = None,
    if_match: str | None = None,
    source: str = "web",
) -> dict:
    """Create or overwrite an exact S3 key and journal the effective operation."""

    s3 = client()
    existed = False
    try:
        s3.head_object(Bucket=bucket, Key=key)
        existed = True
    except Exception as exc:
        status = getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if status not in {404} and code not in {"404", "NoSuchKey", "NotFound"}:
            raise

    kind = "UPDATE" if existed else "PUT"
    started = time.perf_counter()
    params = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentLength": size,
        "ContentType": content_type,
        "Metadata": s3_metadata(metadata),
    }
    if if_match:
        params["IfMatch"] = if_match
    try:
        response = s3.put_object(**params)
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(
            kind=kind,
            success=True,
            bytes_count=size,
            latency_ms=latency,
            bucket=bucket,
            object_key=key,
            client_id=None,
            category=None,
            source=source,
            content_type=content_type,
            error=None,
            request_id=request_id,
            job_id=job_id,
            capacity_decision_id=capacity_decision_id,
            bytes_delta_logical=size,
        )
        return {
            "success": True,
            "operation": kind,
            "bucket": bucket,
            "key": key,
            "size": size,
            "content_type": content_type,
            "etag": response.get("ETag", "").strip('"'),
            "version_id": response.get("VersionId"),
            "latency_ms": round(latency, 2),
        }
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(
            kind=kind,
            success=False,
            bytes_count=0,
            latency_ms=latency,
            bucket=bucket,
            object_key=key,
            client_id=None,
            category=None,
            source=source,
            content_type=content_type,
            error=str(exc)[:1000],
            request_id=request_id,
            job_id=job_id,
            capacity_decision_id=capacity_decision_id,
            error_code="RGW_PUT_FAILED",
        )
        raise


def replace_metadata(
    bucket: str,
    key: str,
    metadata: dict[str, str],
    *,
    content_type: str | None = None,
    version_id: str | None = None,
    request_id: str | None = None,
    capacity_decision_id: str | None = None,
) -> dict:
    s3 = client()
    head_params = {"Bucket": bucket, "Key": key}
    if version_id:
        head_params["VersionId"] = version_id
    head = s3.head_object(**head_params)
    copy_source: dict[str, str] = {"Bucket": bucket, "Key": key}
    if version_id:
        copy_source["VersionId"] = version_id
    started = time.perf_counter()
    try:
        response = s3.copy_object(
            Bucket=bucket,
            Key=key,
            CopySource=copy_source,
            MetadataDirective="REPLACE",
            Metadata=s3_metadata(metadata),
            ContentType=content_type or head.get("ContentType") or "application/octet-stream",
        )
        latency = (time.perf_counter() - started) * 1000
        size = int(head.get("ContentLength") or 0)
        _journal_operation(
            kind="UPDATE",
            success=True,
            bytes_count=size,
            latency_ms=latency,
            bucket=bucket,
            object_key=key,
            client_id=None,
            category=None,
            source="web",
            content_type=content_type or head.get("ContentType"),
            error=None,
            request_id=request_id,
            capacity_decision_id=capacity_decision_id,
            bytes_delta_logical=size,
        )
        return {
            "success": True,
            "operation": "UPDATE",
            "bucket": bucket,
            "key": key,
            "size": size,
            "etag": (response.get("CopyObjectResult") or {}).get("ETag", "").strip('"'),
            "version_id": response.get("VersionId"),
            "metadata": metadata,
            "latency_ms": round(latency, 2),
        }
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(
            kind="UPDATE",
            success=False,
            bytes_count=0,
            latency_ms=latency,
            bucket=bucket,
            object_key=key,
            client_id=None,
            category=None,
            source="web",
            content_type=content_type or head.get("ContentType"),
            error=str(exc)[:1000],
            request_id=request_id,
            capacity_decision_id=capacity_decision_id,
            error_code="RGW_METADATA_UPDATE_FAILED",
        )
        raise


def delete_exact(
    bucket: str,
    key: str,
    *,
    version_id: str | None = None,
    request_id: str | None = None,
    source: str = "web",
) -> dict:
    started = time.perf_counter()
    params = {"Bucket": bucket, "Key": key}
    if version_id:
        params["VersionId"] = version_id
    try:
        response = client().delete_object(**params)
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(
            kind="DELETE",
            success=True,
            bytes_count=0,
            latency_ms=latency,
            bucket=bucket,
            object_key=key,
            client_id=None,
            category=None,
            source=source,
            content_type=None,
            error=None,
            request_id=request_id,
            bytes_delta_logical=0,
        )
        return {
            "success": True,
            "bucket": bucket,
            "key": key,
            "requested_version_id": version_id,
            "deleted_version_id": response.get("VersionId"),
            "delete_marker": bool(response.get("DeleteMarker", False)),
            "hard_delete": True if version_id else None,
            "delete_semantics": "EXACT_VERSION" if version_id else "CURRENT_KEY_MAY_CREATE_MARKER",
            "latency_ms": round(latency, 2),
        }
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        _journal_operation(
            kind="DELETE",
            success=False,
            bytes_count=0,
            latency_ms=latency,
            bucket=bucket,
            object_key=key,
            client_id=None,
            category=None,
            source=source,
            content_type=None,
            error=str(exc)[:1000],
            request_id=request_id,
            error_code="RGW_DELETE_FAILED",
        )
        raise


def list_object_versions(
    bucket: str,
    *,
    prefix: str = "",
    key_marker: str | None = None,
    version_id_marker: str | None = None,
    max_keys: int = 100,
) -> dict:
    params: dict[str, object] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": max_keys}
    if key_marker:
        params["KeyMarker"] = key_marker
    if version_id_marker:
        params["VersionIdMarker"] = version_id_marker
    started = time.perf_counter()
    response = client().list_object_versions(**params)
    latency = (time.perf_counter() - started) * 1000
    rows = []
    for item in response.get("Versions", []):
        rows.append(
            {
                "key": item["Key"],
                "version_id": item.get("VersionId"),
                "is_latest": bool(item.get("IsLatest")),
                "is_delete_marker": False,
                "size": item.get("Size"),
                "etag": item.get("ETag", "").strip('"'),
                "last_modified": item.get("LastModified"),
            }
        )
    for item in response.get("DeleteMarkers", []):
        rows.append(
            {
                "key": item["Key"],
                "version_id": item.get("VersionId"),
                "is_latest": bool(item.get("IsLatest")),
                "is_delete_marker": True,
                "size": 0,
                "etag": None,
                "last_modified": item.get("LastModified"),
            }
        )
    rows.sort(key=lambda row: (row["key"], row.get("last_modified") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    _journal_operation(
        kind="LIST",
        success=True,
        bytes_count=0,
        latency_ms=latency,
        bucket=bucket,
        object_key=prefix or "*",
        client_id=None,
        category=None,
        source="web",
        content_type=None,
        error=None,
    )
    return {
        "versions": rows,
        "is_truncated": bool(response.get("IsTruncated")),
        "next_key_marker": response.get("NextKeyMarker"),
        "next_version_id_marker": response.get("NextVersionIdMarker"),
    }
