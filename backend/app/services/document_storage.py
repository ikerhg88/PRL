from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings

CHUNK_SIZE = 1024 * 1024


class DocumentStorageError(Exception):
    pass


class StoredFileTooLarge(DocumentStorageError):
    pass


class StoredFileNotFound(DocumentStorageError):
    pass


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    path: Path
    sha256: str
    size_bytes: int
    filename: str
    mime_type: str


async def store_upload_file(
    upload_file: UploadFile,
    *,
    tenant_id: int,
    document_id: int,
) -> StoredFile:
    filename = _safe_filename(upload_file.filename or "document.bin")
    relative_path = Path(f"tenant-{tenant_id}") / f"document-{document_id}" / f"{uuid4().hex}-{filename}"
    return await _store_upload_file(upload_file, relative_path=relative_path)


async def store_intake_file(
    upload_file: UploadFile,
    *,
    tenant_id: int,
) -> StoredFile:
    filename = _safe_filename(upload_file.filename or "document.bin")
    relative_path = Path(f"tenant-{tenant_id}") / "intake" / f"{uuid4().hex}-{filename}"
    return await _store_upload_file(upload_file, relative_path=relative_path)


def store_intake_bytes(
    content: bytes,
    *,
    tenant_id: int,
    filename: str,
    mime_type: str = "application/octet-stream",
) -> StoredFile:
    settings = get_settings()
    if len(content) > settings.max_upload_bytes:
        raise StoredFileTooLarge(f"File exceeds max_upload_bytes={settings.max_upload_bytes}")
    safe_name = _safe_filename(filename or "document.bin")
    relative_path = Path(f"tenant-{tenant_id}") / "intake" / f"{uuid4().hex}-{safe_name}"
    root = _storage_root()
    target = _safe_join(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(content)
    except Exception:
        if target.exists():
            target.unlink()
        raise
    return StoredFile(
        storage_key=f"local://{relative_path.as_posix()}",
        path=target,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        filename=safe_name,
        mime_type=mime_type,
    )


async def _store_upload_file(upload_file: UploadFile, *, relative_path: Path) -> StoredFile:
    settings = get_settings()
    root = _storage_root()
    target = _safe_join(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with target.open("wb") as output:
            while chunk := await upload_file.read(CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > settings.max_upload_bytes:
                    raise StoredFileTooLarge(
                        f"File exceeds max_upload_bytes={settings.max_upload_bytes}"
                    )
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        if target.exists():
            target.unlink()
        raise
    finally:
        await upload_file.close()

    storage_key = f"local://{relative_path.as_posix()}"
    return StoredFile(
        storage_key=storage_key,
        path=target,
        sha256=digest.hexdigest(),
        size_bytes=size_bytes,
        filename=_safe_filename(upload_file.filename or "document.bin"),
        mime_type=upload_file.content_type or "application/octet-stream",
    )


def resolve_storage_key(storage_key: str) -> Path:
    if not storage_key.startswith("local://"):
        raise StoredFileNotFound("Unsupported storage key.")
    relative = Path(storage_key.removeprefix("local://"))
    path = _safe_join(_storage_root(), relative)
    if not path.exists() or not path.is_file():
        raise StoredFileNotFound("Stored file not found.")
    return path


def _storage_root() -> Path:
    root = Path(get_settings().document_storage_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_join(root: Path, relative: Path) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise DocumentStorageError("Resolved path escapes storage root.")
    return target


def _safe_filename(filename: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    return normalized[:180] or "document.bin"
