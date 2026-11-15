"""Versioned dataset retrieval, integrity checking, and safe archive extraction."""

import hashlib
import os
import shutil
import tarfile
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import httpx


class DatasetError(RuntimeError):
    """A dataset dependency, download, integrity, or archive failure."""


class DatasetClient:
    def __init__(
        self,
        http: httpx.Client,
        base_url: str,
        storage_root: str | Path | None = None,
        max_bytes: int | None = None,
    ) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.storage_root = Path(storage_root or tempfile.gettempdir()) / "cloudtrain-datasets"
        self.max_bytes = max_bytes or int(os.environ.get("DATASET_MAX_BYTES", str(10 * 1024**3)))

    def download(self, dataset_id: str, version: int) -> Path:
        work = self.storage_root / f"{dataset_id}-v{version}-{uuid.uuid4().hex}"
        archive = work / "dataset.archive"
        extracted = work / "extracted"
        work.mkdir(parents=True)
        try:
            metadata = self._metadata(dataset_id, version)
            actual = self._download(metadata["url"], archive)
            if actual != metadata["checksum_sha256"].lower():
                raise DatasetError(
                    f"dataset checksum mismatch: expected {metadata['checksum_sha256']}, got {actual}"
                )
            extracted.mkdir()
            self._extract(archive, extracted)
            (extracted / ".cloudtrain-checksum-sha256").write_text(actual)
            return extracted
        except Exception:
            shutil.rmtree(work, ignore_errors=True)
            raise

    def cleanup(self, extracted: Path) -> None:
        if extracted.name == "extracted" and extracted.parent.parent == self.storage_root:
            shutil.rmtree(extracted.parent, ignore_errors=True)

    def _metadata(self, dataset_id: str, version: int) -> dict[str, str]:
        url = f"{self.base_url}/internal/datasets/{dataset_id}/versions/{version}/download-url"
        try:
            response = self.http.get(url)
            response.raise_for_status()
            body = response.json()
            download_url = body["url"]
            checksum = body["checksum_sha256"]
            if not isinstance(download_url, str) or not isinstance(checksum, str):
                raise TypeError("url and checksum_sha256 must be strings")
            invalid_character = any(character not in "0123456789abcdefABCDEF" for character in checksum)
            if len(checksum) != 64 or invalid_character:
                raise ValueError("checksum_sha256 must be a 64-character hexadecimal digest")
            return {"url": download_url, "checksum_sha256": checksum}
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise DatasetError(f"dataset metadata dependency failed: {error}") from error

    def _download(self, url: str, destination: Path) -> str:
        digest = hashlib.sha256()
        size = 0
        try:
            with self.http.stream("GET", url) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise DatasetError(f"dataset download exceeds {self.max_bytes} bytes")
                        digest.update(chunk)
                        output.write(chunk)
        except httpx.HTTPError as error:
            raise DatasetError(f"dataset download failed: {error}") from error
        return digest.hexdigest()

    def _extract(self, archive: Path, destination: Path) -> None:
        try:
            if zipfile.is_zipfile(archive):
                self._extract_zip(archive, destination)
            elif tarfile.is_tarfile(archive):
                self._extract_tar(archive, destination)
            else:
                # CSV uploads arrive as a single file, not an archive.
                target = destination / "dataset.csv"
                shutil.copyfile(archive, target)
                try:
                    sample = target.read_text(encoding="utf-8-sig")
                except UnicodeDecodeError as error:
                    raise DatasetError(
                        "single-file dataset must be a UTF-8 CSV or a zip/tar archive"
                    ) from error
                if "," not in sample.splitlines()[0]:
                    raise DatasetError("single-file dataset is not a CSV header row")
        except DatasetError:
            raise
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
            raise DatasetError(f"dataset archive could not be extracted: {error}") from error

    @staticmethod
    def _safe_target(destination: Path, member_name: str) -> Path:
        path = PurePosixPath(member_name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise DatasetError(f"unsafe dataset archive path: {member_name}")
        target = destination.joinpath(*path.parts).resolve()
        if destination.resolve() not in target.parents and target != destination.resolve():
            raise DatasetError(f"unsafe dataset archive path: {member_name}")
        return target

    def _extract_zip(self, archive: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                target = self._safe_target(destination, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_file, target.open("wb") as output:
                    shutil.copyfileobj(input_file, output)

    def _extract_tar(self, archive: Path, destination: Path) -> None:
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                target = self._safe_target(destination, member.name)
                if member.issym() or member.islnk() or member.isdev():
                    raise DatasetError(f"unsafe dataset archive member: {member.name}")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    input_file = source.extractfile(member)
                    if input_file is None:
                        raise DatasetError(f"dataset archive member is unreadable: {member.name}")
                    with input_file, target.open("wb") as output:
                        shutil.copyfileobj(input_file, output)
