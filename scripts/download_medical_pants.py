#!/usr/bin/env python3
"""Download, verify and safely extract the pinned public PanTSMini release.

This prepares raw files only: it does not create a training split or authorize use
of the official test set for training. Original archives are always retained.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY = "BodyMaps/PanTSMini"
REVISION = "3b1cd61108116b58ea5c1ddb3512c1847d965f96"
LABEL_URL = "https://www.cs.jhu.edu/~zongwei/dataset/PanTSMini_Label.tar.gz"
LABEL_ETAG = '"39f906de5-6469033c15f5e"'
LABEL_LAST_MODIFIED = "Mon, 22 Dec 2025 20:23:37 GMT"
CHUNK = 8 * 1024 * 1024
CASE = re.compile(r"PanTS_(\d{8})\Z")
MASK = re.compile(r"[a-z][a-z0-9_]*\.nii\.gz\Z")


@dataclasses.dataclass(frozen=True)
class Archive:
    name: str
    size: int
    sha256: str | None
    kind: str
    first: int = 0
    last: int = 0

    @property
    def source(self) -> str:
        if self.kind == "labels":
            return LABEL_URL
        return f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{self.name}"


# File sizes and SHA-256 are the LFS objects returned by the pinned Hub tree API.
# The separate JHU label release has no published cryptographic checksum. Its
# ETag is retained as an HTTP validator, never represented as an MD5 or SHA hash.
ARCHIVES = (
    Archive(
        "metadata.xlsx",
        1334813,
        "4bcbf14a31b1ca9441af051a104702e7a832391f47d3af5f493048ec813283e3",
        "metadata",
    ),
    Archive(
        "PanTSMini_ImageTr_00000001_00001000.tar.gz",
        34190903436,
        "c6a1e4e67617940a3e86da4362fc8c753d7bbc2e592181e347060dc3689af078",
        "images",
        1,
        1000,
    ),
    Archive(
        "PanTSMini_ImageTr_00001001_00002000.tar.gz",
        35596328294,
        "2bfecfb93a73d4814826727d22ba587c902dfd08f282d2e7559063bd12746c3f",
        "images",
        1001,
        2000,
    ),
    Archive(
        "PanTSMini_ImageTr_00002001_00003000.tar.gz",
        35984898422,
        "ac8b0f8aafab554ee9aeb4133835b7f8e1a85902899afda8cab47be0cc64d640",
        "images",
        2001,
        3000,
    ),
    Archive(
        "PanTSMini_ImageTr_00003001_00004000.tar.gz",
        35096498961,
        "5099f3b4435492d01b876d4027f8b7b937fef57c2b52a7daf6dc581233716de4",
        "images",
        3001,
        4000,
    ),
    Archive(
        "PanTSMini_ImageTr_00004001_00005000.tar.gz",
        36652762963,
        "406f864d59393000e38f1225d48f2b0dcae980e1138f02f6ed4a4b554f030328",
        "images",
        4001,
        5000,
    ),
    Archive(
        "PanTSMini_ImageTr_00005001_00006000.tar.gz",
        34946274132,
        "1ea4d4ee015257367d57dae1fdfab111581cff7062e76cb59735e89d332b4aa3",
        "images",
        5001,
        6000,
    ),
    Archive(
        "PanTSMini_ImageTr_00006001_00007000.tar.gz",
        34799850880,
        "75c83106a511795cd29151a718cc1cd6ee4ca940f015e5273653ea6e2b4462be",
        "images",
        6001,
        7000,
    ),
    Archive(
        "PanTSMini_ImageTr_00007001_00008000.tar.gz",
        34771850148,
        "8bc56bb40ab0ddbd34b20a40b368e418be8fa7fc0283b20c0f593056bf853045",
        "images",
        7001,
        8000,
    ),
    Archive(
        "PanTSMini_ImageTr_00008001_00009000.tar.gz",
        35668462502,
        "c450c191c3469727c5e2b02179b1b66392dcd67791d6b3c93bb7cc23effcfb5b",
        "images",
        8001,
        9000,
    ),
    Archive(
        "PanTSMini_ImageTe_00009001_00009901.tar.gz",
        27994666473,
        "a7930a2ed1d5638f334ac6614a30b1474832c7dbf24d228a19c5ecba7fe9d7aa",
        "images",
        9001,
        9901,
    ),
    Archive("PanTSMini_Label.tar.gz", 15561944549, None, "labels", 1, 9901),
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(CHUNK):
            result.update(block)
    return result.hexdigest()


def signature(path: Path) -> dict[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular, non-symlink file: {path}")
    stat = path.stat()
    return {
        key: int(getattr(stat, key))
        for key in ("st_size", "st_mtime_ns", "st_ctime_ns", "st_dev", "st_ino")
    }


def ensure_directory(path: Path) -> None:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError(f"Refusing symlink directory: {ancestor}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"Not a directory: {path}")


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    ensure_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError(f"Refusing symlink state file: {path}")
    return json.loads(path.read_text())


def state_path(root: Path, archive: Archive) -> Path:
    return root / "state" / f"{archive.name}.json"


@contextlib.contextmanager
def lock(root: Path) -> Iterator[None]:
    ensure_directory(root / "state")
    path = root / "state" / "prepare.lock"
    if path.is_symlink():
        raise ValueError("Refusing symlink lock")
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another PanTS preparation process holds the lock") from error
        yield


def verify(root: Path, archive: Archive, *, rehash: bool = False) -> dict[str, Any]:
    path = root / "archives" / archive.name
    before = signature(path)
    if before["st_size"] != archive.size:
        raise ValueError(
            f"Incomplete or wrong-sized archive {archive.name}: {before['st_size']} != {archive.size}"
        )
    previous = read_json(state_path(root, archive))
    spec = dataclasses.asdict(archive)
    if (
        not rehash
        and previous.get("spec") == spec
        and previous.get("archive_stat") == before
        and previous.get("archive_sha256")
    ):
        return previous
    actual = digest(path)
    if signature(path) != before:
        raise ValueError(f"Archive changed during verification: {archive.name}")
    if archive.sha256 is not None and actual != archive.sha256:
        raise ValueError(
            f"Provider SHA-256 mismatch: {archive.name}; original file preserved, no automatic replacement"
        )
    if previous.get("archive_sha256") not in (None, actual):
        raise ValueError(
            f"Previously recorded archive changed: {archive.name}; original evidence preserved"
        )
    record = {
        "schema_version": 1,
        "spec": spec,
        "archive_stat": before,
        "archive_sha256": actual,
        "source": archive.source,
        "provider_sha256_verified": archive.sha256 is not None,
        "integrity_note": "Provider LFS SHA-256 matched"
        if archive.sha256
        else "Local SHA-256 only; JHU publishes no checksum. Gzip CRC is checked during extraction and is not source authentication.",
        "verified_at": utc_now(),
        "status": "verified",
        "gzip_crc_verified": False,
    }
    if previous.get("status") == "extracted" and previous.get("archive_sha256") == actual:
        record.update(
            {
                key: previous[key]
                for key in ("status", "gzip_crc_verified", "cases", "files", "extracted_at")
                if key in previous
            }
        )
    atomic_json(state_path(root, archive), record)
    return record


def validate_member(member: tarfile.TarInfo, archive: Archive) -> tuple[str, str] | None:
    raw = member.name
    if raw.startswith("./"):
        raw = raw[2:]
    if raw in ("", ".") and member.isdir():
        return None
    if raw.endswith("/") and not member.isdir():
        raise ValueError(f"Regular archive file has a directory suffix: {member.name!r}")
    # Validate raw components before pathlib can normalize away a traversal.
    pieces = raw.rstrip("/").split("/")
    if (
        any(part in ("", ".", "..") for part in pieces)
        or "\\" in raw
        or PurePosixPath(raw).is_absolute()
    ):
        raise ValueError(f"Unsafe archive path: {member.name!r}")
    match = CASE.fullmatch(pieces[0])
    if match is None or not archive.first <= int(match[1]) <= archive.last:
        raise ValueError(f"Case outside the pinned archive range: {member.name!r}")
    if (
        member.issym()
        or member.islnk()
        or member.sparse is not None
        or not (member.isfile() or member.isdir())
    ):
        raise ValueError(
            f"Links, sparse files and special archive members are forbidden: {member.name!r}"
        )
    relative = "/".join(pieces[1:])
    if member.isdir():
        allowed = len(pieces) == 1 or (archive.kind == "labels" and relative == "segmentations")
    elif archive.kind == "images":
        allowed = relative == "ct.nii.gz"
    else:
        allowed = relative == "combined_labels.nii.gz" or (
            len(pieces) == 3 and pieces[1] == "segmentations" and bool(MASK.fullmatch(pieces[2]))
        )
    if not allowed:
        raise ValueError(f"Unexpected member layout: {member.name!r}")
    if member.isfile() and not 0 < member.size <= 4 * 1024**3:
        raise ValueError(f"Invalid or excessive member size: {member.name!r}")
    return pieces[0], relative


def destination(root: Path, archive: Archive, case: str) -> Path:
    suffix = "Tr" if int(case.removeprefix("PanTS_")) <= 9000 else "Te"
    return root / "data" / f"{'Image' if archive.kind == 'images' else 'Label'}{suffix}" / case


def check_case(path: Path, files: dict[str, dict[str, Any]], *, rehash: bool = False) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    actual: set[str] = set()
    for item in path.rglob("*"):
        if item.is_symlink():
            return False
        if item.is_file():
            actual.add(item.relative_to(path).as_posix())
    if actual != set(files):
        return False
    for relative, info in files.items():
        member = path / relative
        if signature(member)["st_size"] != info["size"]:
            return False
        if (rehash or signature(member) != info.get("stat")) and digest(member) != info["sha256"]:
            return False
    return True


def extracted_intact(
    root: Path, archive: Archive, record: dict[str, Any], *, rehash: bool = False
) -> bool:
    cases = record.get("files", {})
    if archive.kind == "metadata":
        target = root / "data" / archive.name
        return (
            record.get("status") == "extracted"
            and target.is_file()
            and not target.is_symlink()
            and digest(target) == archive.sha256
        )
    expected = {f"PanTS_{number:08d}" for number in range(archive.first, archive.last + 1)}
    return (
        record.get("status") == "extracted"
        and set(cases) == expected
        and all(
            check_case(destination(root, archive, case), files, rehash=rehash)
            for case, files in cases.items()
        )
    )


def extract(root: Path, archive: Archive, *, rehash: bool = False) -> dict[str, Any]:
    record = verify(root, archive, rehash=rehash)
    ensure_directory(root / "data")
    if extracted_intact(root, archive, record, rehash=rehash):
        return record
    if record.get("status") == "extracted":
        raise ValueError(
            f"Previously extracted data changed or disappeared: {archive.name}; refusing silent overwrite"
        )
    if archive.kind == "metadata":
        target = root / "data" / archive.name
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_file() or digest(target) != archive.sha256:
                raise ValueError(f"Conflicting metadata destination already exists: {target}")
            record.update(status="extracted", extracted_at=utc_now(), cases=0)
            atomic_json(state_path(root, archive), record)
            return record
        temporary = root / "data" / ".metadata.xlsx.partial"
        if temporary.is_symlink():
            raise ValueError("Refusing symlink staging file")
        shutil.copyfile(root / "archives" / archive.name, temporary)
        os.replace(temporary, target)
        record.update(status="extracted", extracted_at=utc_now(), cases=0)
        atomic_json(state_path(root, archive), record)
        return record
    # Retain the same staging tree on interruption. Existing files are checked
    # against streamed archive bytes before reuse; ready cases publish only after
    # every header, the exact case set and the final gzip CRC have been validated.
    stage = root / "state" / "staging" / archive.name
    ensure_directory(stage)
    for parent in ("ImageTr", "ImageTe", "LabelTr", "LabelTe"):
        ensure_directory(root / "data" / parent)
    seen: set[str] = set()
    files: dict[str, dict[str, Any]] = {}
    expanded = 0
    record.update(status="extracting", started_at=utc_now())
    atomic_json(state_path(root, archive), record)
    with gzip.open(root / "archives" / archive.name, "rb") as decoded:
        with tarfile.open(fileobj=decoded, mode="r|", ignore_zeros=True) as tar:
            for member in tar:
                validated = validate_member(member, archive)
                if validated is None:
                    if "." in seen:
                        raise ValueError("Duplicate archive root directory")
                    seen.add(".")
                    continue
                case, relative = validated
                canonical = f"{case}/{relative}".rstrip("/")
                if canonical in seen:
                    raise ValueError(f"Duplicate archive path: {canonical}")
                seen.add(canonical)
                if member.isdir():
                    continue
                expanded += member.size
                if expanded > archive.size * 4 + 1024**3:
                    raise ValueError("Archive exceeds its bounded expansion limit")
                case_dir = stage / case
                ensure_directory(case_dir)
                target = case_dir / relative
                ensure_directory(target.parent)
                if target.is_symlink():
                    raise ValueError(f"Refusing symlink staged file: {target}")
                temporary: Path | None = None
                try:
                    result = hashlib.sha256()
                    count = 0
                    source = tar.extractfile(member)
                    if source is None:
                        raise ValueError("Missing archive member data")
                    with source, contextlib.ExitStack() as stack:
                        output = None
                        if not target.exists():
                            descriptor, temporary_name = tempfile.mkstemp(
                                prefix=".member-", dir=target.parent
                            )
                            temporary = Path(temporary_name)
                            output = stack.enter_context(os.fdopen(descriptor, "wb"))
                        while block := source.read(CHUNK):
                            if output is not None:
                                output.write(block)
                            result.update(block)
                            count += len(block)
                    if count != member.size:
                        raise ValueError("Truncated archive member")
                    expected_hash = result.hexdigest()
                    if target.exists():
                        if not target.is_file() or digest(target) != expected_hash:
                            raise ValueError(
                                f"Conflicting staged file: {target}; preserved for inspection"
                            )
                    else:
                        if temporary is None:
                            raise ValueError("Staged file disappeared during extraction")
                        os.replace(temporary, target)
                    files.setdefault(case, {})[relative] = {"sha256": expected_hash, "size": count}
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                if len(files) % 100 == 0 and len(files[case]) == 1:
                    atomic_json(
                        root / "state" / "progress.json",
                        {
                            "archive": archive.name,
                            "status": "extracting",
                            "cases_staged": len(files),
                            "expanded_bytes": expanded,
                            "updated_at": utc_now(),
                        },
                    )
        # tarfile can stop at a logical tar terminator; draining explicitly
        # ensures truncated/corrupt gzip trailers are rejected before publishing.
        while decoded.read(CHUNK):
            pass
    if signature(root / "archives" / archive.name) != record["archive_stat"]:
        raise ValueError("Archive changed during extraction")
    expected = {f"PanTS_{number:08d}" for number in range(archive.first, archive.last + 1)}
    if set(files) != expected:
        raise ValueError(f"Incomplete archive case coverage: {len(files)} != {len(expected)}")
    if archive.kind == "images" and any(set(value) != {"ct.nii.gz"} for value in files.values()):
        raise ValueError("An image case does not contain exactly ct.nii.gz")
    record.update(status="publishing", gzip_crc_verified=True, cases=len(files), files=files)
    atomic_json(state_path(root, archive), record)
    for case, members in files.items():
        target = destination(root, archive, case)
        if target.exists() or target.is_symlink():
            if not check_case(target, members, rehash=True):
                raise ValueError(f"Conflicting existing case: {target}; refusing overwrite")
        else:
            os.rename(stage / case, target)
        for relative, info in members.items():
            info["stat"] = signature(target / relative)
    record.update(status="extracted", extracted_at=utc_now())
    atomic_json(state_path(root, archive), record)
    return record


def label_headers() -> dict[str, str]:
    request = urllib.request.Request(LABEL_URL, method="HEAD")
    with urllib.request.urlopen(request, timeout=60) as response:
        result = {key.lower(): value for key, value in response.headers.items()}
    if (
        int(result.get("content-length", "-1")) != ARCHIVES[-1].size
        or result.get("etag") != LABEL_ETAG
    ):
        raise ValueError(
            "JHU label release HTTP size/ETag changed; review a new release instead of silently resuming"
        )
    return {key: result.get(key, "") for key in ("content-length", "etag", "last-modified")}


def download(root: Path, archive: Archive, *, attempts: int = 3, hf: str = "hf") -> None:
    ensure_directory(root / "archives")
    path = root / "archives" / archive.name
    if path.exists() or path.is_symlink():
        verify(root, archive)
        return
    if archive.kind == "labels":
        headers = label_headers()
        atomic_json(
            root / "provenance" / "label-http.json",
            {
                "source": LABEL_URL,
                "checked_at": utc_now(),
                "headers": headers,
                "note": "HTTP validators, not cryptographic source hashes",
            },
        )
    for attempt in range(attempts):
        if archive.kind == "labels":
            partial = path.with_suffix(path.suffix + ".partial")
            if partial.is_symlink():
                raise ValueError("Refusing symlink partial download")
            command = [
                "curl",
                "--fail",
                "--location",
                "--connect-timeout",
                "30",
                "--speed-limit",
                "1024",
                "--speed-time",
                "120",
                "--continue-at",
                "-",
                "--header",
                f"If-Match: {LABEL_ETAG}",
                "--output",
                str(partial),
                LABEL_URL,
            ]
        else:
            command = [
                hf,
                "download",
                REPOSITORY,
                archive.name,
                "--repo-type",
                "dataset",
                "--revision",
                REVISION,
                "--local-dir",
                str(root / "archives"),
            ]
        completed = subprocess.run(command, check=False)
        if completed.returncode == 0:
            if archive.kind == "labels":
                if partial.stat().st_size != archive.size:
                    raise ValueError(
                        "Label download returned the wrong size; partial file preserved"
                    )
                os.replace(partial, path)
            verify(root, archive)
            return
        if attempt + 1 < attempts:
            time.sleep(min(60, 2 ** (attempt + 1)))
    raise RuntimeError(
        f"Download failed after {attempts} attempts: {archive.name}; partial files preserved"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", "download", "verify", "extract"), default="all")
    parser.add_argument(
        "--verify-extract-only",
        action="store_true",
        help="Alias for --stage extract; never accesses the network",
    )
    parser.add_argument(
        "--archive",
        action="append",
        choices=[item.name for item in ARCHIVES],
        help="Process only named files; repeat for a subset",
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--hf", default="hf", help="Path to the installed Hugging Face CLI")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="For verify/extract: process complete files as an external downloader finishes them",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=172800,
        help="Maximum watch duration; never retries a corrupt complete archive",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument(
        "--rehash",
        action="store_true",
        help="Rehash archives and extracted files instead of reusing unchanged filesystem signatures",
    )
    parser.add_argument("--nice", type=int, default=10, choices=range(20), metavar="0..19")
    args = parser.parse_args(argv)
    if not 1 <= args.attempts <= 10:
        parser.error("--attempts must be between 1 and 10")
    if args.verify_extract_only and args.stage not in ("all", "extract"):
        parser.error("--verify-extract-only conflicts with --stage")
    stage = "extract" if args.verify_extract_only else args.stage
    if args.watch and stage not in ("verify", "extract"):
        parser.error("--watch requires --stage verify/extract or --verify-extract-only")
    if not 1 <= args.poll_seconds <= 60 or not 1 <= args.wait_seconds <= 604800:
        parser.error("--poll-seconds must be 1..60 and --wait-seconds must be 1..604800")
    root = args.root.expanduser().resolve()
    ensure_directory(root)
    for name in ("archives", "data", "provenance", "state", "logs"):
        ensure_directory(root / name)
    if args.nice:
        os.nice(args.nice)
    selected = [item for item in ARCHIVES if not args.archive or item.name in args.archive]
    with lock(root):
        atomic_json(
            root / "provenance" / "release.json",
            {
                "repository": REPOSITORY,
                "revision": REVISION,
                "archives": [
                    dataclasses.asdict(item) | {"source": item.source} for item in ARCHIVES
                ],
                "label_http_etag": LABEL_ETAG,
                "label_http_last_modified": LABEL_LAST_MODIFIED,
                "label_checksum_scope": "Locally calculated SHA-256 and gzip CRC; no provider cryptographic checksum published",
                "official_training_cases": 9000,
                "official_test_cases": 901,
                "training_readiness": "Raw download/extraction only; metadata, masks, geometry, patient grouping and overlap audits are separate requirements",
            },
        )
        pending = list(selected)
        deadline = time.monotonic() + args.wait_seconds
        while pending:
            for archive in list(pending):
                path = root / "archives" / archive.name
                if (
                    args.watch
                    and not path.is_symlink()
                    and (not path.exists() or path.stat().st_size < archive.size)
                ):
                    continue
                print(
                    json.dumps({"archive": archive.name, "stage": stage, "started_at": utc_now()}),
                    flush=True,
                )
                try:
                    if stage in ("all", "download"):
                        download(root, archive, attempts=args.attempts, hf=args.hf)
                    if stage == "verify":
                        verify(root, archive, rehash=args.rehash)
                    if stage in ("all", "extract"):
                        extract(root, archive, rehash=args.rehash)
                except Exception as error:
                    atomic_json(
                        root / "state" / "progress.json",
                        {
                            "archive": archive.name,
                            "status": "failed",
                            "error_type": type(error).__name__,
                            "updated_at": utc_now(),
                        },
                    )
                    raise
                pending.remove(archive)
                summary = {
                    "archive": archive.name,
                    "status": read_json(state_path(root, archive)).get("status", "downloaded"),
                    "archives_remaining": len(pending),
                    "archives_selected": len(selected),
                    "updated_at": utc_now(),
                }
                atomic_json(root / "state" / "progress.json", summary)
                print(json.dumps(summary), flush=True)
            if pending:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Timed out waiting for {len(pending)} archives; verified/extracted evidence preserved"
                    )
                summary = {
                    "status": "waiting_for_downloads",
                    "archives_remaining": len(pending),
                    "archives_selected": len(selected),
                    "updated_at": utc_now(),
                }
                atomic_json(root / "state" / "progress.json", summary)
                print(json.dumps(summary), flush=True)
                time.sleep(min(args.poll_seconds, max(0, deadline - time.monotonic())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
