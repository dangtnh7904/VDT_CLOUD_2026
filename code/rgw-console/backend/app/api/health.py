from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..db import connection
from ..services.executor_client import ExecutorClient, ExecutorClientError
from ..storage import client as s3_client


router = APIRouter(tags=["health"])


def _feature_flags(settings: Settings) -> dict[str, bool]:
    return {
        "upgrade": settings.feature_upgrade,
        "lab": settings.feature_lab,
        "legacy_rgw": settings.feature_legacy_rgw,
        "legacy_rbd": settings.feature_legacy_rbd,
    }


def _unavailable(*, required: bool, code: str) -> dict[str, Any]:
    return {"status": "unavailable", "required": required, "code": code}


def _database_status() -> dict[str, Any]:
    try:
        with connection() as conn:
            row = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
        if not row:
            return _unavailable(required=True, code="SCHEMA_VERSION_MISSING")
        return {
            "status": "ready",
            "required": True,
            "schema_version": row["version"],
        }
    except Exception:
        # Health responses intentionally expose a stable code, not connection
        # strings, SQL text or other exception details.
        return _unavailable(required=True, code="DATABASE_OR_SCHEMA_UNAVAILABLE")


def _frontend_status(settings: Settings) -> dict[str, Any]:
    if settings.frontend_dist_path is None:
        return {"status": "disabled", "required": False}
    try:
        root = settings.frontend_dist_path.resolve(strict=True)
    except OSError:
        return _unavailable(required=True, code="FRONTEND_DIST_UNAVAILABLE")
    if not root.is_dir() or not (root / "index.html").is_file():
        return _unavailable(required=True, code="FRONTEND_INDEX_MISSING")
    return {"status": "ready", "required": True}


def _rgw_status(settings: Settings) -> dict[str, Any]:
    if not settings.feature_legacy_rgw:
        return {"status": "disabled", "required": False}
    if not all(
        (settings.rgw_endpoint_url, settings.rgw_access_key, settings.rgw_secret_key)
    ):
        return _unavailable(required=True, code="RGW_CONFIG_INVALID")
    try:
        response = s3_client().list_buckets()
        visible = [
            row
            for row in response.get("Buckets", [])
            if row.get("Name") in settings.rgw_allowed_bucket_set
        ]
        return {
            "status": "ready",
            "required": True,
            "endpoint": settings.rgw_endpoint_url,
            "visible_buckets": len(visible),
            "bucket_scope": "CURRENT_S3_IDENTITY",
        }
    except Exception:
        return _unavailable(required=True, code="RGW_UNAVAILABLE")


def _executor_status(settings: Settings) -> dict[str, Any]:
    required_by = []
    if settings.feature_upgrade:
        required_by.append("upgrade")
    if settings.feature_legacy_rbd:
        required_by.append("legacy_rbd")
    if settings.feature_lab and settings.lab_validation_enabled:
        required_by.append("lab")
    if not required_by:
        return {"status": "disabled", "required": False}
    if not settings.ceph_expected_fsid or not settings.effective_executor_token:
        return _unavailable(required=True, code="EXECUTOR_CONFIG_INVALID")
    try:
        token = settings.effective_executor_token
        ExecutorClient(
            settings.effective_executor_url,
            token=token.get_secret_value() if token else "",
            expected_fsid=settings.ceph_expected_fsid or "",
            timeout_seconds=settings.rbd_executor_timeout_seconds,
            osd_info_timeout_seconds=settings.osd_info_collector_timeout_seconds,
            osd_info_max_response_bytes=settings.osd_info_collector_max_output_bytes,
        ).health()
        return {
            "status": "ready",
            "required": True,
            "required_by": required_by,
        }
    except ExecutorClientError as exc:
        return _unavailable(required=True, code=exc.code)
    except Exception:
        return _unavailable(required=True, code="EXECUTOR_UNAVAILABLE")


def readiness_snapshot(settings: Settings | None = None) -> tuple[dict[str, Any], int]:
    """Build a feature-aware readiness result without leaking secret values."""

    settings = settings or get_settings()
    try:
        settings.validate_feature_dependencies()
        config_status: dict[str, Any] = {"status": "ready", "required": True}
    except ValueError as exc:
        config_status = _unavailable(required=True, code="FEATURE_CONFIG_INVALID")
        # validate_feature_dependencies reports missing field names only.
        config_status["reason"] = str(exc)

    dependencies = {
        "config": config_status,
        "database": _database_status(),
        "frontend": _frontend_status(settings),
        "rgw": _rgw_status(settings),
        "ceph_executor": _executor_status(settings),
    }
    blocking = sorted(
        name
        for name, state in dependencies.items()
        if state.get("required") and state.get("status") != "ready"
    )
    ready = not blocking
    return (
        {
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "features": _feature_flags(settings),
            "dependencies": dependencies,
            "blocking_dependencies": blocking,
        },
        200 if ready else 503,
    )


@router.get("/api/live")
def liveness() -> dict[str, str]:
    # Deliberately process-only: optional dependency failure must not create a
    # restart loop.
    return {"status": "ok"}


@router.get("/api/ready")
def readiness():
    payload, status_code = readiness_snapshot()
    if status_code == 200:
        return payload
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/api/health/dependencies")
def dependency_health():
    payload, status_code = readiness_snapshot()
    if status_code == 200:
        return payload
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/api/health")
def compatibility_health():
    """Preserve the legacy path while using feature-aware readiness."""

    payload, status_code = readiness_snapshot()
    rgw = payload["dependencies"]["rgw"]
    response = {
        **payload,
        "status": "ok" if payload["ready"] else "degraded",
        "endpoint": rgw.get("endpoint"),
        "buckets": rgw.get("visible_buckets"),
        "bucket_scope": rgw.get("bucket_scope"),
        "schema_version": payload["dependencies"]["database"].get("schema_version"),
    }
    if status_code == 200:
        return response
    return JSONResponse(status_code=status_code, content=response)
