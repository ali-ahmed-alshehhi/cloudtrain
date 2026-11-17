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
