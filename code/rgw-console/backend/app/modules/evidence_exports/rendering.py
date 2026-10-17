from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from ..osd_info_collector.redaction import redact_collector_evidence


REDACTION_VERSION = "export-v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 20_000
MAX_NODES = 200_000
_SECRET_KEY = re.compile(
    r"(^|[_-])(authorization|password|passwd|secret|access_key|credential|keyring|token|private_key|database_url)([_-]|$)",
    re.IGNORECASE,
)
_FILESYSTEM_REF = re.compile(r"filesystem:[^\s\"'<>]+", re.IGNORECASE)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----", re.DOTALL)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|password|passwd|token|secret(?:[_-]key)?|access[_-]key|keyring)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_AUTH_HEADER = re.compile(r"(?i)\b(?:Basic|Bearer)\s+[A-Za-z0-9+/=._-]{8,}")
_URL = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+")
_URI_FIELDS = {"uri", "evidence_uri", "artifact_uri", "store_uri", "filesystem_uri"}


class ExportError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _redact_string(value: str) -> str:
    value = _PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", value)
    value = _FILESYSTEM_REF.sub("[EVIDENCE_REF]", value)
    value = _AUTH_HEADER.sub("[REDACTED_AUTHORIZATION]", value)
    value = _SECRET_ASSIGNMENT.sub(lambda match: match.group(1) + "=[REDACTED]", value)

    def redact_url(match):
        try:
            url = urlsplit(match.group(0))
            if url.username or url.password or url.query:
                return "[REDACTED_URL]"
        except ValueError:
            return "[REDACTED_URL]"
        return match.group(0)

    return _URL.sub(redact_url, value)


def safe_projection(value: Any) -> Any:
    """A new copy, never a mutation or hash of the immutable source bytes."""
    nodes = 0
    string_bytes = 0

    def canonical(item: Any, depth: int = 0):
        nonlocal nodes, string_bytes
        nodes += 1
        if nodes > MAX_NODES or depth > 32:
            raise ExportError("EXPORT_LIMIT_EXCEEDED", "Evidence projection exceeds synchronous export limits", 413)
        if isinstance(item, (datetime, date, UUID, Enum)):
            item = item.value if isinstance(item, Enum) else str(item)
        if isinstance(item, Decimal):
            item = str(item)
        if isinstance(item, float) and not math.isfinite(item):
            raise ExportError("EXPORT_SOURCE_INVALID", "Evidence contains a non-finite numeric value")
        if isinstance(item, str):
            string_bytes += len(item.encode("utf-8"))
            if string_bytes > MAX_BYTES:
                raise ExportError("EXPORT_LIMIT_EXCEEDED", "Evidence text exceeds synchronous export limits", 413)
            return _redact_string(item)
        if item is None or isinstance(item, (bool, int, float)):
            return item
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ExportError("EXPORT_SOURCE_INVALID", "Evidence object keys are invalid")
            return {
                _redact_string(key): "[REDACTED]" if _SECRET_KEY.search(key) else canonical(child, depth + 1)
                for key, child in item.items() if key.lower() not in _URI_FIELDS
            }
        if isinstance(item, (list, tuple)):
            if len(item) > MAX_ROWS:
                raise ExportError("EXPORT_LIMIT_EXCEEDED", "Evidence table exceeds synchronous export row limits", 413)
            return [canonical(child, depth + 1) for child in item]
        raise ExportError("EXPORT_SOURCE_INVALID", "Evidence is not a supported JSON projection")

    return redact_collector_evidence(canonical(value))


def json_bytes(value: Any, *, compact: bool = False) -> bytes:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=None if compact else 2,
        separators=(",", ":") if compact else None, allow_nan=False,
    ).encode("utf-8") + b"\n"
    if len(encoded) > MAX_BYTES:
        raise ExportError("EXPORT_LIMIT_EXCEEDED", "Export exceeds the 16 MiB synchronous download limit", 413)
    return encoded


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            result.update(_flatten(child, path))
        elif isinstance(child, list):
            result[path] = json.dumps(child, ensure_ascii=False, sort_keys=True, allow_nan=False)
        else:
            result[path] = child
    return result


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and re.match(r"^[\s\x00-\x1f]*[=+@-]", value):
        return "'" + value
    return value


def csv_bytes(tables: dict[str, list[dict]], manifest: dict) -> bytes:
    rows = []
    context = {
        "_export_id": manifest["export_id"], "_cluster_id": manifest.get("cluster_id"),
        "_fsid": manifest.get("fsid"), "_quality": manifest.get("quality"),
    }
    for name, records in tables.items():
        for record in records:
            flattened = _flatten(record)
            if any(key.startswith("_") for key in flattened):
                # Source data cannot overwrite the export's reserved columns.
                flattened = {"data." + key if key.startswith("_") else key: child for key, child in flattened.items()}
            rows.append({
                **flattened, **context, "_record_type": name,
                "_null_fields": json.dumps(sorted(key for key, child in flattened.items() if child is None)),
            })
            if len(rows) > MAX_ROWS:
                raise ExportError("EXPORT_LIMIT_EXCEEDED", "Export exceeds synchronous CSV row limits", 413)
    if not rows:
        rows = [{
            **context, "_record_type": "metadata", "state": manifest.get("quality"),
            "reasons": json.dumps(manifest.get("reasons", []), ensure_ascii=False),
            "_null_fields": "[]",
        }]
    metadata_headers = ["_record_type", "_export_id", "_cluster_id", "_fsid", "_quality", "_null_fields"]
    headers = metadata_headers + sorted(set().union(*(row.keys() for row in rows)) - set(metadata_headers))
    if len(headers) > 512:
        raise ExportError("EXPORT_LIMIT_EXCEEDED", "Export exceeds synchronous CSV column limits", 413)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([_csv_cell(header) for header in headers])
    for row in rows:
        writer.writerow([_csv_cell(row.get(header)) for header in headers])
        if output.tell() > MAX_BYTES:
            raise ExportError("EXPORT_LIMIT_EXCEEDED", "CSV exceeds the synchronous export limit", 413)
    encoded = output.getvalue().encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ExportError("EXPORT_LIMIT_EXCEEDED", "CSV exceeds the synchronous export limit", 413)
    return encoded


def markdown_bytes(data: dict, manifest: dict) -> bytes:
    document = json_bytes({"manifest": manifest, "data": data}).decode("utf-8")
    # An untrusted string containing backticks cannot break out of the JSON block.
    longest_fence = max((len(match.group(0)) for match in re.finditer(r"`+", document)), default=0)
    fence = "`" * max(3, longest_fence + 1)
    title = html.escape(str(manifest["source"])).replace("`", "\\`")
    encoded = (
        f"# Storage Lab Console — {title}\n\n"
        f"Export ID: {manifest['export_id']}\n\n"
        "This is a redacted copy of existing evidence, not a live validation or a cluster mutation. "
        "Unavailable metrics remain null. Source hashes and download hashes are distinct.\n\n"
        f"{fence}json\n{document}{fence}\n"
    ).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ExportError("EXPORT_LIMIT_EXCEEDED", "Markdown exceeds the synchronous export limit", 413)
    return encoded


@dataclass(frozen=True)
class ExportDownload:
    content: bytes
    filename: str
    mime_type: str
    sha256: str
    export_id: str
    manifest: dict


def render_export(*, data: dict, tables: dict[str, list[dict]], raw: dict[str, Any], manifest: dict, format: str) -> ExportDownload:
    # Check canonical payload sizes before building alternative representations.
    data_json = json_bytes(data)
    if format == "json":
        content = json_bytes({"manifest": manifest, "data": data})
        mime = "application/json"
    elif format == "csv":
        content = csv_bytes(tables, manifest)
        mime = "text/csv; charset=utf-8"
    elif format == "md":
        content = markdown_bytes(data, manifest)
        mime = "text/markdown; charset=utf-8"
    elif format == "zip":
        # Machine-readable ZIP members need not multiply pretty-print whitespace.
        # The human-readable report and all existing safety bounds are retained.
        payloads = {"data/summary.json": json_bytes(data, compact=True), "data/records.csv": csv_bytes(tables, manifest)}
        for index, (_, value) in enumerate(sorted(raw.items())):
            payloads[f"raw-redacted/{index + 1:03d}.json"] = json_bytes(value, compact=True)
        payloads["report.md"] = markdown_bytes(data, manifest)
        if sum(len(value) for value in payloads.values()) > MAX_BYTES:
            raise ExportError("EXPORT_LIMIT_EXCEEDED", "Uncompressed bundle exceeds the 16 MiB export limit", 413)
        manifest = {**manifest, "files": [
            {"path": name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
            for name, content in sorted(payloads.items())
        ]}
        payloads["manifest.json"] = json_bytes(manifest)
        payloads["SHA256SUMS"] = "".join(
            f"{hashlib.sha256(value).hexdigest()}  {name}\n" for name, value in sorted(payloads.items())
        ).encode("utf-8")
        if sum(len(value) for value in payloads.values()) > MAX_BYTES:
            raise ExportError("EXPORT_LIMIT_EXCEEDED", "Bundle metadata exceeds the synchronous export limit", 413)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, value in sorted(payloads.items()):
                archive.writestr(name, value)
        content = output.getvalue()
        mime = "application/zip"
    else:
        raise ExportError("EXPORT_FORMAT_UNSUPPORTED", "Requested export format is unsupported", 422)
    if len(content) > MAX_BYTES:
        raise ExportError("EXPORT_LIMIT_EXCEEDED", "Download exceeds the 16 MiB synchronous export limit", 413)
    cluster = re.sub(r"[^A-Za-z0-9._-]", "-", str(manifest.get("cluster_id") or "unconfigured"))[:64]
    timestamp = re.sub(r"[^0-9T]", "", manifest["exported_at"].split(".")[0])
    filename = f"storage-lab_{cluster}_{manifest['source']}_{timestamp}_{manifest['export_id']}.{format}"
    return ExportDownload(content, filename, mime, hashlib.sha256(content).hexdigest(), manifest["export_id"], manifest)
