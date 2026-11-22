"""Settings must load wherever the code lives: in the repo, and in the image at /service/app."""

from pathlib import Path

from app import settings


def test_repo_schema_is_found_from_the_repo():
    path = settings._repo_schema(Path(settings.__file__))
    assert path is not None and path.exists()


def test_shallow_image_path_does_not_crash():
    # /service/app/settings.py is three folders deep, with no repo above it (the old code raised IndexError).
    assert settings._repo_schema(Path("/service/app/settings.py")) is None


def test_shallow_path_falls_back_to_the_image_schema(monkeypatch):
    monkeypatch.setattr(settings, "_IMAGE_SCHEMA", Path("/nowhere/job-event.schema.json"))
    assert settings._default_schema(Path("/service/app/settings.py")) == "/nowhere/job-event.schema.json"
