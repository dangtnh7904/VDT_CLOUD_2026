import mimetypes
import random
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException

from .config import get_settings


CATEGORY_ALIASES = {
    "image": "images", "images": "images",
    "document": "documents", "documents": "documents",
    "presentation": "documents", "spreadsheet": "data",
    "data": "data", "text": "data", "source-code": "data",
    "video": "media", "audio": "media", "media": "media",
    "archive": "archives", "archives": "archives",
    "binary": "binary", "edge-cases": "other", "other": "other",
}


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime.startswith("image/"):
        return "images"
    if mime.startswith(("video/", "audio/")):
        return "media"
    if suffix in {".zip", ".7z", ".tar", ".gz", ".bz2", ".xz", ".rar"}:
        return "archives"
    if suffix in {".pdf", ".doc", ".docx", ".odt", ".rtf", ".ppt", ".pptx", ".odp", ".epub"}:
        return "documents"
    if suffix in {".json", ".csv", ".tsv", ".parquet", ".xml", ".yaml", ".yml", ".xls", ".xlsx", ".ods", ".sqlite"} or mime.startswith("text/"):
        return "data"
    if suffix == ".bin":
        return "binary"
    return "other"


def resolve_corpus_path(corpus_id: str, relative_path: str = "") -> tuple[Path, Path]:
    roots = get_settings().corpus_roots
    if corpus_id not in roots:
        raise HTTPException(404, "Unknown corpus")
    root = roots[corpus_id]
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(403, "Path is outside the corpus allowlist")
    if not candidate.exists():
        raise HTTPException(404, "Corpus path does not exist")
    return root, candidate


def describe(path: Path, root: Path) -> dict:
    is_dir = path.is_dir()
    return {
        "name": path.name,
        "path": path.relative_to(root).as_posix() if path != root else "",
        "kind": "directory" if is_dir else "file",
        "size": None if is_dir else path.stat().st_size,
        "category": None if is_dir else classify(path),
        "extension": "" if is_dir else path.suffix.lower().lstrip("."),
        "content_type": None if is_dir else (mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
    }


def all_files(corpus_ids: Iterable[str] = ("mixed", "size")) -> list[tuple[str, Path, Path]]:
    found: list[tuple[str, Path, Path]] = []
    for corpus_id in corpus_ids:
        root, _ = resolve_corpus_path(corpus_id)
        found.extend((corpus_id, root, path) for path in root.rglob("*") if path.is_file())
    return found


def choose_random(corpus_ids: list[str], category: str | None, extension: str | None, min_bytes: int | None, max_bytes: int | None) -> tuple[str, Path, Path]:
    candidates = all_files(corpus_ids)
    extension = extension.lower().lstrip(".") if extension else None
    candidates = [item for item in candidates if not category or classify(item[2]) == CATEGORY_ALIASES.get(category, category)]
    candidates = [item for item in candidates if not extension or item[2].name.lower().endswith(f".{extension}")]
    candidates = [item for item in candidates if min_bytes is None or item[2].stat().st_size >= min_bytes]
    candidates = [item for item in candidates if max_bytes is None or item[2].stat().st_size <= max_bytes]
    if not candidates:
        raise HTTPException(404, "No corpus file matches these filters")
    return random.choice(candidates)

