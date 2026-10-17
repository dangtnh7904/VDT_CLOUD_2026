"""Print non-secret release and embedded component metadata as JSON."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path


ROOT = Path("/opt/storage-lab-console")
COLLECTOR = ROOT / "collector" / "collect_osd.py"
MIGRATIONS = ROOT / "backend" / "app" / "migrations" / "versions"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collector_metadata() -> tuple[str, int]:
    source = COLLECTOR.read_text(encoding="utf-8")
    version = re.search(r'^COLLECTOR_VERSION\s*=\s*"([^"]+)"', source, re.MULTILINE)
    schema = re.search(r"^SCHEMA_VERSION\s*=\s*(\d+)", source, re.MULTILINE)
    if version is None or schema is None:
        raise RuntimeError("collector version metadata is missing")
    return version.group(1), int(schema.group(1))


def _database_schema() -> int:
    versions = [
        int(match.group(1))
        for path in MIGRATIONS.glob("*.sql")
        if (match := re.match(r"(\d{4})_", path.name))
    ]
    if not versions:
        raise RuntimeError("database migrations are missing")
    return max(versions)


collector_version, collector_schema = _collector_metadata()
print(
    json.dumps(
        {
            "application_version": os.environ.get("APP_VERSION", "unknown"),
            "revision": os.environ.get("APP_REVISION", "unknown"),
            "built_at": os.environ.get("APP_BUILD_DATE", "unknown"),
            "config_schema": os.environ.get("APP_CONFIG_SCHEMA_VERSION", "unknown"),
            "database_schema": _database_schema(),
            "collector": {
                "version": collector_version,
                "schema": collector_schema,
                "sha256": _sha256(COLLECTOR),
            },
        },
        sort_keys=True,
    )
)
