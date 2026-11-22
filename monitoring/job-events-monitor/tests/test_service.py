from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from tests.conftest import FIXTURE_TWO_ATTEMPTS, FakeQueue


def client_with(queue, metrics):
    app = create_app(settings=Settings(), queue=queue, metrics=metrics, start_consumer=False)
    return app, TestClient(app)


def test_health_is_503_until_the_queue_was_read_then_200(metrics):
    queue = FakeQueue()
    app, client = client_with(queue, metrics)
    with client:
        answer = client.get("/health")
        assert answer.status_code == 503
        assert answer.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
        app.state.consumer.poll_once()
        assert client.get("/health").json() == {"status": "ok", "service": "job-events-monitor"}


def test_metrics_endpoint_and_shared_error_format(metrics):
    queue = FakeQueue()
    queue.put(*FIXTURE_TWO_ATTEMPTS)
    app, client = client_with(queue, metrics)
    with client:
        app.state.consumer.poll_once()
        assert client.get("/metrics").status_code == 200
        missing = client.get("/nope", headers={"X-Request-Id": "req-test"})
        assert missing.status_code == 404
        assert missing.json()["error"]["request_id"] == "req-test"
        assert missing.headers["X-Request-Id"] == "req-test"


def test_every_series_starts_at_zero_so_the_first_events_are_counted(metrics, registry, schema):
    # Seen on a laptop (20 Nov): 3 jobs succeeded but the dashboard showed 1, because the series appeared
    # only at the first event and Prometheus first saw it at 2 or 3. Now each one exists at 0 from the start.
    assert registry.get_sample_value("cloudtrain_job_events_total", {"event_type": "job.succeeded"}) is None
    client_with(FakeQueue(), metrics)
    for event_type in schema["properties"]["event_type"]["enum"]:
        assert registry.get_sample_value("cloudtrain_job_events_total", {"event_type": event_type}) == 0.0
    for result in ("SUCCEEDED", "FAILED", "CANCELLED"):
        assert registry.get_sample_value("cloudtrain_job_run_seconds_count", {"result": result}) == 0.0
    for reason in ("not_json", "schema", "bad_time"):
        assert registry.get_sample_value("cloudtrain_job_events_invalid_total", {"reason": reason}) == 0.0
