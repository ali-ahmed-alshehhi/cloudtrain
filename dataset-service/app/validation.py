"""Check that an uploaded file really matches the declared format (csv, zip, tar_gz)."""

import io
import tarfile
import zipfile


def matches_format(file_format: str, data: bytes) -> bool:
    if file_format == "csv":
        try:
            return len(data) > 0 and "," in data.decode("utf-8").splitlines()[0]
        except (UnicodeDecodeError, IndexError):
            return False
    if file_format == "zip":
        return zipfile.is_zipfile(io.BytesIO(data))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz"):
            return True
    except (tarfile.TarError, OSError, EOFError):
        return False
