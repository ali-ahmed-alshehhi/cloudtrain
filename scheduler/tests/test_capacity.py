"""Tests for the capacity tracker."""

from app.capacity import CapacityTracker


def test_reserve_and_release():
    cap = CapacityTracker(max_workers=2)
    assert cap.has_capacity()
    assert cap.reserve("job-1", "local-cpu")
    assert cap.active_count == 1
    assert cap.has_capacity()
    assert cap.reserve("job-2", "g4dn.xlarge")
    assert cap.active_count == 2
    assert not cap.has_capacity()

    released = cap.release("job-1")
    assert released == "local-cpu"
    assert cap.active_count == 1
    assert cap.has_capacity()


def test_reserve_fails_when_full():
    cap = CapacityTracker(max_workers=1)
    assert cap.reserve("job-1", "local-cpu")
    assert not cap.reserve("job-2", "g4dn.xlarge")


def test_reserve_fails_for_duplicate_job():
    cap = CapacityTracker(max_workers=2)
    assert cap.reserve("job-1", "local-cpu")
    assert not cap.reserve("job-1", "local-cpu")


def test_release_unknown_job_returns_none():
    cap = CapacityTracker(max_workers=1)
    assert cap.release("job-999") is None


def test_gpu_in_use():
    cap = CapacityTracker(max_workers=4)
    cap.reserve("job-1", "local-cpu")
    cap.reserve("job-2", "g4dn.xlarge")
    cap.reserve("job-3", "g4dn.12xlarge")
    assert cap.gpu_in_use() == 5  # 0 + 1 + 4


def test_active_jobs_snapshot():
    cap = CapacityTracker(max_workers=2)
    cap.reserve("job-1", "c6i.2xlarge")
    snap = cap.active_jobs
    assert snap == {"job-1": "c6i.2xlarge"}
    # snapshot is a copy, not a live view
    cap.reserve("job-2", "local-cpu")
    assert "job-2" not in snap
