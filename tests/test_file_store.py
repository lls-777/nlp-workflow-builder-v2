from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

import storage.file_store as file_store_module
from storage.file_store import FileStore, FileStoreError


FILE_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def file_store(tmp_path: Path) -> FileStore:
    allowed_source_dir = tmp_path / "allowed"
    allowed_source_dir.mkdir()
    return FileStore(
        uploads_dir=tmp_path / "uploads",
        artifacts_dir=tmp_path / "artifacts",
        allowed_source_roots=(allowed_source_dir,),
    )


def test_file_store_saves_uuid_upload_name(file_store: FileStore) -> None:
    stored_path = file_store.save_upload(
        original_filename="../../notes.txt",
        content=b"safe upload",
        file_id=FILE_ID,
    )

    assert stored_path.name == f"{FILE_ID}.txt"
    assert stored_path.read_bytes() == b"safe upload"
    assert file_store.resolve_upload(stored_path) == stored_path


def test_file_store_copies_only_allowed_source(file_store: FileStore) -> None:
    source_path = file_store.allowed_source_roots[0] / "faq.md"
    source_path.write_text("# FAQ", encoding="utf-8")

    stored_path = file_store.copy_allowed_upload(source_path, file_id=FILE_ID)

    assert stored_path.name == f"{FILE_ID}.md"
    assert stored_path.read_text(encoding="utf-8") == "# FAQ"


def test_file_store_rejects_arbitrary_system_path(file_store: FileStore) -> None:
    with pytest.raises(FileStoreError, match="outside allowed roots"):
        file_store.copy_allowed_upload("/etc/hosts")


def test_file_store_rejects_upload_path_traversal(file_store: FileStore) -> None:
    traversal_path = file_store.uploads_dir / ".." / "outside.txt"

    with pytest.raises(FileStoreError, match="outside allowed root"):
        file_store.resolve_upload(traversal_path)


def test_file_store_rejects_upload_symlink_escape(
    file_store: FileStore,
    tmp_path: Path,
) -> None:
    outside_path = tmp_path / "outside.txt"
    outside_path.write_text("outside", encoding="utf-8")
    link_path = file_store.uploads_dir / "outside-link.txt"
    os.symlink(outside_path, link_path)

    with pytest.raises(FileStoreError, match="outside allowed root"):
        file_store.resolve_upload(link_path)


def test_file_store_rejects_more_than_ten_uploads(file_store: FileStore) -> None:
    uploads = tuple((f"file-{index}.txt", b"x") for index in range(11))

    with pytest.raises(FileStoreError, match="最多只能上传 10 个文件"):
        file_store.save_uploads(uploads=uploads)


def test_file_store_rejects_total_upload_size_before_writing(
    file_store: FileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_store_module, "MAX_TOTAL_FILE_BYTES", 5)

    with pytest.raises(FileStoreError, match="总计不能超过 50MB"):
        file_store.save_uploads(
            uploads=(("first.txt", b"123"), ("second.txt", b"456")),
        )

    assert not tuple(file_store.uploads_dir.iterdir())
