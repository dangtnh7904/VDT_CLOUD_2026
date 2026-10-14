from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True)
class StoredArtifact:
    id: UUID
    uri: str
    sha256: str
    size_bytes: int
    mime_type: str


class FilesystemArtifactStore:
    """Bounded append-only JSON artifact store for lab deployments."""

    def __init__(self, root: Path, *, max_artifact_bytes: int) -> None:
        self.root = root.resolve()
        self.max_artifact_bytes = max_artifact_bytes
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be positive")

    def put_json(
        self,
        payload: object,
        *,
        cluster_id: str,
        session_id: UUID,
        run_id: UUID,
    ) -> StoredArtifact:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(encoded) > self.max_artifact_bytes:
            raise ValueError("evidence artifact exceeds EVIDENCE_MAX_ARTIFACT_BYTES")
        artifact_id = uuid4()
        relative = Path(cluster_id) / str(session_id) / str(run_id) / f"{artifact_id}.json"
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("evidence path escaped EVIDENCE_ROOT")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredArtifact(
            id=artifact_id,
            uri=f"filesystem:{relative.as_posix()}",
            sha256=hashlib.sha256(encoded).hexdigest(),
            size_bytes=len(encoded),
            mime_type="application/json",
        )

    def read_json(
        self,
        uri: str,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> object:
        """Read a stored JSON artifact only after containment and integrity checks."""

        prefix = "filesystem:"
        if not isinstance(uri, str) or not uri.startswith(prefix):
            raise ValueError("unsupported evidence artifact URI")
        relative_text = uri[len(prefix):]
        relative = Path(relative_text)
        if not relative_text or relative.is_absolute():
            raise ValueError("evidence artifact URI must contain a relative path")
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("evidence path escaped EVIDENCE_ROOT")
        if (
            not isinstance(expected_size_bytes, int)
            or isinstance(expected_size_bytes, bool)
            or expected_size_bytes < 0
            or expected_size_bytes > self.max_artifact_bytes
        ):
            raise ValueError("evidence artifact size is outside configured bounds")
        if not target.is_file():
            raise ValueError("evidence artifact is not a regular file")
        observed_size = target.stat().st_size
        if observed_size != expected_size_bytes or observed_size > self.max_artifact_bytes:
            raise ValueError("evidence artifact size does not match its registry entry")
        with target.open("rb") as handle:
            encoded = handle.read(self.max_artifact_bytes + 1)
        if len(encoded) != expected_size_bytes:
            raise ValueError("evidence artifact size changed while reading")
        observed_sha256 = hashlib.sha256(encoded).hexdigest()
        if not hmac.compare_digest(observed_sha256, expected_sha256):
            raise ValueError("evidence artifact SHA-256 does not match its registry entry")
        try:
            return json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("evidence artifact is not valid UTF-8 JSON") from exc
