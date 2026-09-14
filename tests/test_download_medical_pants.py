"""PanTS preparation preserves source evidence and fails closed on unsafe input."""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import io
import subprocess
import tarfile
from pathlib import Path
from typing import ClassVar

import pytest
from scripts import download_medical_pants as pants


def make_archive(
    root: Path,
    members: list[tuple[str, bytes | None]],
    *,
    kind: str = "images",
    first: int = 1,
    last: int = 1,
    provider: bool = True,
    special: bytes | None = None,
) -> pants.Archive:
    path = root / "archives" / "test.tar.gz"
    path.parent.mkdir(exist_ok=True)
    with tarfile.open(path, "w:gz") as stream:
        for name, data in members:
            member = tarfile.TarInfo(name)
            if data is None:
                member.type = tarfile.DIRTYPE
            elif special is not None:
                member.type = special
                member.linkname = "../../escape"
            else:
                member.size = len(data)
            stream.addfile(member, io.BytesIO(data) if data else None)
    sha = hashlib.sha256(path.read_bytes()).hexdigest() if provider else None
    return pants.Archive(path.name, path.stat().st_size, sha, kind, first, last)


def test_pinned_release_has_exact_expected_coverage() -> None:
    images = [item for item in pants.ARCHIVES if item.kind == "images"]
    cases = [number for item in images for number in range(item.first, item.last + 1)]
    assert sorted(cases) == list(range(1, 9902))
    assert len(cases) == len(set(cases))
    assert len(pants.ARCHIVES) == 12
    assert all(item.sha256 and len(item.sha256) == 64 for item in pants.ARCHIVES[:-1])
    assert pants.ARCHIVES[-1].sha256 is None
    assert pants.ARCHIVES[-1].size == 15561944549


def test_extract_and_resume_preserves_original_and_avoids_rehash(tmp_path, monkeypatch) -> None:
    archive = make_archive(
        tmp_path, [("./PanTS_00000001/", None), ("PanTS_00000001/ct.nii.gz", b"ct")]
    )
    first = pants.extract(tmp_path, archive)
    target = tmp_path / "data/ImageTr/PanTS_00000001/ct.nii.gz"
    assert target.read_bytes() == b"ct"
    assert first["provider_sha256_verified"] is True
    assert first["gzip_crc_verified"] is True
    assert first["status"] == "extracted"
    assert (tmp_path / "archives" / archive.name).is_file()
    monkeypatch.setattr(
        pants, "digest", lambda _: pytest.fail("Unchanged verified files were rehashed")
    )
    assert pants.extract(tmp_path, archive) == first
    monkeypatch.setattr(
        pants.subprocess, "run", lambda *a, **k: pytest.fail("Redownloaded valid archive")
    )
    pants.download(tmp_path, archive)


def test_label_layout_retains_combined_and_separates_official_test(tmp_path) -> None:
    archive = make_archive(
        tmp_path,
        [
            ("PanTS_00009001/combined_labels.nii.gz", b"combined"),
            ("PanTS_00009001/segmentations/pancreas.nii.gz", b"pancreas"),
        ],
        kind="labels",
        first=9001,
        last=9001,
        provider=False,
    )
    result = pants.extract(tmp_path, archive)
    assert result["provider_sha256_verified"] is False
    assert result["archive_sha256"]
    assert result["gzip_crc_verified"] is True
    assert (
        tmp_path / "data/LabelTe/PanTS_00009001/combined_labels.nii.gz"
    ).read_bytes() == b"combined"
    assert not list((tmp_path / "data/LabelTr").iterdir())


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/PanTS_00000001/ct.nii.gz",
        "PanTS_00000001/../ct.nii.gz",
        "PanTS_00000001//ct.nii.gz",
        "PanTS_00000001\\ct.nii.gz",
        "PanTS_00000002/ct.nii.gz",
        "PanTS_00000001/secret.txt",
        "././PanTS_00000001/ct.nii.gz",
    ],
)
def test_rejects_traversal_ranges_and_unexpected_files(tmp_path, name) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"valid"), (name, b"bad")])
    with pytest.raises(ValueError):
        pants.extract(tmp_path, archive)
    assert not list((tmp_path / "data/ImageTr").iterdir())
    assert (tmp_path / "archives" / archive.name).is_file()


@pytest.mark.parametrize(
    "special",
    [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE],
)
def test_rejects_links_and_special_members(tmp_path, special) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"x")], special=special)
    with pytest.raises(ValueError, match="forbidden"):
        pants.extract(tmp_path, archive)


def test_rejects_duplicate_normalized_paths(tmp_path) -> None:
    archive = make_archive(
        tmp_path, [("PanTS_00000001/ct.nii.gz", b"one"), ("./PanTS_00000001/ct.nii.gz", b"two")]
    )
    with pytest.raises(ValueError, match="Duplicate"):
        pants.extract(tmp_path, archive)
    assert not list((tmp_path / "data/ImageTr").iterdir())


def test_requires_complete_case_range_before_publication(tmp_path) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")], last=2)
    with pytest.raises(ValueError, match="coverage"):
        pants.extract(tmp_path, archive)
    assert not list((tmp_path / "data/ImageTr").iterdir())


def test_provider_hash_mismatch_stops_without_overwriting(tmp_path, monkeypatch) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")])
    archive = dataclasses.replace(archive, sha256="0" * 64)
    original = (tmp_path / "archives" / archive.name).read_bytes()
    monkeypatch.setattr(
        pants.subprocess, "run", lambda *a, **k: pytest.fail("Retried invalid complete file")
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        pants.download(tmp_path, archive)
    assert (tmp_path / "archives" / archive.name).read_bytes() == original


def test_gzip_crc_must_validate_before_cases_publish(tmp_path) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")], provider=False)
    path = tmp_path / "archives" / archive.name
    data = bytearray(path.read_bytes())
    data[-8] ^= 1
    path.write_bytes(data)
    with pytest.raises((gzip.BadGzipFile, tarfile.ReadError)):
        pants.extract(tmp_path, archive)
    assert not list((tmp_path / "data/ImageTr").iterdir())


def test_resume_after_partial_case_publication(tmp_path, monkeypatch) -> None:
    archive = make_archive(
        tmp_path,
        [("PanTS_00000002/ct.nii.gz", b"two"), ("PanTS_00000001/ct.nii.gz", b"one")],
        last=2,
    )
    original_rename = pants.os.rename
    calls = 0

    def interrupt(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated process interruption")
        return original_rename(source, target)

    monkeypatch.setattr(pants.os, "rename", interrupt)
    with pytest.raises(RuntimeError, match="interruption"):
        pants.extract(tmp_path, archive)
    assert len(list((tmp_path / "data/ImageTr").iterdir())) == 1
    monkeypatch.setattr(pants.os, "rename", original_rename)
    result = pants.extract(tmp_path, archive)
    assert result["status"] == "extracted"
    assert len(list((tmp_path / "data/ImageTr").iterdir())) == 2


def test_modified_extracted_data_is_not_silently_replaced(tmp_path) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")])
    pants.extract(tmp_path, archive)
    target = tmp_path / "data/ImageTr/PanTS_00000001/ct.nii.gz"
    target.write_bytes(b"bad")
    with pytest.raises(ValueError, match="Previously extracted data changed"):
        pants.extract(tmp_path, archive)
    assert target.read_bytes() == b"bad"


def test_conflicting_case_is_preserved(tmp_path) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")])
    target = tmp_path / "data/ImageTr/PanTS_00000001"
    target.mkdir(parents=True)
    (target / "ct.nii.gz").write_bytes(b"other")
    with pytest.raises(ValueError, match="Conflicting existing case"):
        pants.extract(tmp_path, archive)
    assert (target / "ct.nii.gz").read_bytes() == b"other"


def test_symlink_staging_ancestor_is_rejected(tmp_path) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")])
    (tmp_path / "state").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "state/staging").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        pants.extract(tmp_path, archive)
    assert not list(outside.iterdir())


def test_download_uses_pinned_hf_cli_and_bounded_retries(tmp_path, monkeypatch) -> None:
    archive = pants.Archive("metadata.xlsx", 3, hashlib.sha256(b"xls").hexdigest(), "metadata")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if len(commands) < 3:
            return subprocess.CompletedProcess(command, 1)
        (tmp_path / "archives/metadata.xlsx").write_bytes(b"xls")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(pants.subprocess, "run", fake_run)
    monkeypatch.setattr(pants.time, "sleep", lambda _: None)
    pants.download(tmp_path, archive, hf="/env/bin/hf")
    assert len(commands) == 3
    assert commands[0][:4] == ["/env/bin/hf", "download", pants.REPOSITORY, "metadata.xlsx"]
    assert commands[0][commands[0].index("--revision") + 1] == pants.REVISION


def test_watch_processes_available_files_then_exits_without_network(tmp_path, monkeypatch) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")])
    monkeypatch.setattr(pants, "ARCHIVES", (archive,))
    monkeypatch.setattr(
        pants.subprocess, "run", lambda *a, **k: pytest.fail("Watch touched network")
    )
    assert (
        pants.main(["--root", str(tmp_path), "--verify-extract-only", "--watch", "--nice", "0"])
        == 0
    )
    summary = pants.read_json(tmp_path / "state/progress.json")
    assert summary["archives_remaining"] == 0
    assert "PanTS_00000001" not in str(summary)


def test_watch_timeout_preserves_incomplete_archive(tmp_path, monkeypatch) -> None:
    archive = make_archive(tmp_path, [("PanTS_00000001/ct.nii.gz", b"one")])
    archive = dataclasses.replace(archive, size=archive.size + 1)
    monkeypatch.setattr(pants, "ARCHIVES", (archive,))
    clock = iter([0, 2])
    monkeypatch.setattr(pants.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError):
        pants.main(
            [
                "--root",
                str(tmp_path),
                "--verify-extract-only",
                "--watch",
                "--wait-seconds",
                "1",
                "--nice",
                "0",
            ]
        )
    assert (tmp_path / "archives" / archive.name).is_file()


def test_label_release_headers_are_http_validators_not_hashes(monkeypatch) -> None:
    class Response:
        headers: ClassVar[dict[str, str]] = {
            "Content-Length": str(pants.ARCHIVES[-1].size),
            "ETag": pants.LABEL_ETAG,
            "Last-Modified": pants.LABEL_LAST_MODIFIED,
        }

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(pants.urllib.request, "urlopen", lambda *a, **k: Response())
    assert pants.label_headers()["etag"] == pants.LABEL_ETAG
    Response.headers["ETag"] = '"different"'
    with pytest.raises(ValueError, match="changed"):
        pants.label_headers()
