"""Histogram buckets fine enough for short laptop jobs as well as long GPU jobs."""

from prometheus_client import CollectorRegistry

from app.metrics import RUN_BUCKETS, WAIT_BUCKETS, Metrics


def test_buckets_are_sorted_and_reach_hours():
    for buckets in (WAIT_BUCKETS, RUN_BUCKETS):
        assert list(buckets) == sorted(buckets)
        assert buckets[-1] >= 3600


def test_a_short_laptop_job_lands_in_a_small_bucket():
    # Test D (22 Nov): queue wait about 0.036 s, training about 3 s. Each must land below 1 s / 10 s,
    # otherwise p50 and p95 can only say "under the first bucket".
    registry = CollectorRegistry()
    metrics = Metrics(registry)
    metrics.queue_wait.observe(0.036)
    metrics.run.labels("SUCCEEDED").observe(3.0)
    assert registry.get_sample_value("cloudtrain_job_queue_wait_seconds_bucket", {"le": "0.1"}) == 1.0
    run = "cloudtrain_job_run_seconds_bucket"
    assert registry.get_sample_value(run, {"result": "SUCCEEDED", "le": "5.0"}) == 1.0
    assert registry.get_sample_value(run, {"result": "SUCCEEDED", "le": "2.5"}) == 0.0
