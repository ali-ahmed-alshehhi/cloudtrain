"""Unit tests for machine-type selection."""

import os

from app.machines import pick_machine


def test_local_always_returns_local_cpu(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    assert pick_machine(0) == "local-cpu"
    assert pick_machine(1) == "local-cpu"
    assert pick_machine(4) == "local-cpu"


def test_cloud_cpu_job():
    os.environ["ENVIRONMENT"] = "cloud"
    try:
        assert pick_machine(0) == "c6i.2xlarge"
    finally:
        os.environ["ENVIRONMENT"] = "local"


def test_cloud_single_gpu():
    os.environ["ENVIRONMENT"] = "cloud"
    try:
        assert pick_machine(1) == "g4dn.xlarge"
    finally:
        os.environ["ENVIRONMENT"] = "local"


def test_cloud_multi_gpu():
    os.environ["ENVIRONMENT"] = "cloud"
    try:
        assert pick_machine(2) == "g4dn.12xlarge"
        assert pick_machine(4) == "g4dn.12xlarge"
    finally:
        os.environ["ENVIRONMENT"] = "local"


def test_default_environment_is_local():
    os.environ.pop("ENVIRONMENT", None)
    assert pick_machine(4) == "local-cpu"