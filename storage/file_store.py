from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple, Union
from uuid import UUID, uuid4

from config import (
    ALLOWED_FILE_ROOTS,
    ARTIFACTS_DIR,
    MAX_SINGLE_FILE_BYTES,
    MAX_TOTAL_FILE_BYTES,
    MAX_UPLOAD_FILES,
    SUPPORTED_UPLOAD_EXTENSIONS,
    UPLOADS_DIR,
)


class FileStoreError(ValueError):
    """Raised when a local file cannot be stored safely."""


class FileStore:
    def __init__(
        self,
        *,
        uploads_dir: Union[str, Path] = UPLOADS_DIR,
        artifacts_dir: Union[str, Path] = ARTIFACTS_DIR,
        allowed_source_roots: Sequence[Path] = ALLOWED_FILE_ROOTS,
    ) -> None:
        self.uploads_dir = Path(uploads_dir).resolve()
        self.artifacts_dir = Path(artifacts_dir).resolve()
        self.allowed_source_roots = tuple(
            Path(root).resolve() for root in allowed_source_roots
        )
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(
        self,
        *,
        original_filename: str,
        content: bytes,
        file_id: Optional[UUID] = None,
    ) -> Path:
        self._validate_upload_batch(
            uploads=((original_filename, content),),
            existing_paths=(),
        )
        return self._write_upload(
            original_filename=original_filename,
            content=content,
            file_id=file_id,
        )

    def save_uploads(
        self,
        *,
        uploads: Sequence[Tuple[str, bytes]],
        existing_paths: Sequence[Union[str, Path]] = (),
    ) -> Sequence[Path]:
        normalized_uploads = tuple(uploads)
        self._validate_upload_batch(
            uploads=normalized_uploads,
            existing_paths=existing_paths,
        )
        return tuple(
            self._write_upload(
                original_filename=original_filename,
                content=content,
            )
            for original_filename, content in normalized_uploads
        )

    def resolve_uploads(
        self,
        stored_paths: Sequence[Union[str, Path]],
    ) -> Sequence[Path]:
        resolved_paths = tuple(self.resolve_upload(path) for path in stored_paths)
        _validate_file_limits(resolved_paths)
        return resolved_paths

    def _write_upload(
        self,
        *,
        original_filename: str,
        content: bytes,
        file_id: Optional[UUID] = None,
    ) -> Path:
        if not isinstance(content, bytes):
            raise FileStoreError("Uploaded file content must be bytes.")
        extension = _validated_extension(original_filename)
        destination = (self.uploads_dir / f"{file_id or uuid4()}{extension}").resolve()
        _require_within_root(destination, self.uploads_dir)
        try:
            destination.write_bytes(content)
        except OSError as exc:
            raise FileStoreError("Unable to save uploaded file.") from exc
        return destination

    def _validate_upload_batch(
        self,
        *,
        uploads: Sequence[Tuple[str, bytes]],
        existing_paths: Sequence[Union[str, Path]],
    ) -> None:
        resolved_existing = tuple(
            self.resolve_upload(path) for path in existing_paths
        )
        upload_sizes = []
        for original_filename, content in uploads:
            if not isinstance(content, bytes):
                raise FileStoreError("Uploaded file content must be bytes.")
            _validated_extension(original_filename)
            if len(content) > MAX_SINGLE_FILE_BYTES:
                raise FileStoreError("单个文件不能超过 20MB。")
            upload_sizes.append(len(content))
        total_count = len(resolved_existing) + len(uploads)
        total_bytes = sum(path.stat().st_size for path in resolved_existing)
        total_bytes += sum(upload_sizes)
        _validate_batch_limits(total_count=total_count, total_bytes=total_bytes)

    def copy_allowed_upload(
        self,
        source_path: Union[str, Path],
        *,
        file_id: Optional[UUID] = None,
    ) -> Path:
        source = Path(source_path).resolve()
        _require_within_any_root(source, self.allowed_source_roots)
        if not source.is_file():
            raise FileStoreError(f"Source file does not exist: {source}")
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise FileStoreError(f"Unable to read source file: {source.name}") from exc
        return self.save_upload(
            original_filename=source.name,
            content=content,
            file_id=file_id,
        )

    def resolve_upload(self, stored_path: Union[str, Path]) -> Path:
        resolved_path = Path(stored_path).resolve()
        _require_within_root(resolved_path, self.uploads_dir)
        if not resolved_path.is_file():
            raise FileStoreError(f"Uploaded file does not exist: {resolved_path}")
        return resolved_path

    def save_artifact(
        self,
        *,
        original_filename: str,
        content: bytes,
        file_id: Optional[UUID] = None,
    ) -> Path:
        if not isinstance(content, bytes):
            raise FileStoreError("Artifact content must be bytes.")
        extension = Path(original_filename).suffix.lower()
        destination = (self.artifacts_dir / f"{file_id or uuid4()}{extension}").resolve()
        _require_within_root(destination, self.artifacts_dir)
        try:
            destination.write_bytes(content)
        except OSError as exc:
            raise FileStoreError("Unable to save artifact.") from exc
        return destination


def _validated_extension(original_filename: str) -> str:
    extension = Path(original_filename).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise FileStoreError(
            f"Unsupported uploaded file format: {extension or '<none>'}"
        )
    return extension


def _require_within_any_root(path: Path, roots: Iterable[Path]) -> None:
    for root in roots:
        try:
            path.relative_to(root.resolve())
            return
        except ValueError:
            continue
    raise FileStoreError(f"File path is outside allowed roots: {path}")


def _require_within_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise FileStoreError(f"File path is outside allowed root: {path}") from exc


def _validate_file_limits(paths: Sequence[Path]) -> None:
    for path in paths:
        if path.stat().st_size > MAX_SINGLE_FILE_BYTES:
            raise FileStoreError("单个文件不能超过 20MB。")
    _validate_batch_limits(
        total_count=len(paths),
        total_bytes=sum(path.stat().st_size for path in paths),
    )


def _validate_batch_limits(*, total_count: int, total_bytes: int) -> None:
    if total_count > MAX_UPLOAD_FILES:
        raise FileStoreError("最多只能上传 10 个文件。")
    if total_bytes > MAX_TOTAL_FILE_BYTES:
        raise FileStoreError("上传文件总计不能超过 50MB。")
