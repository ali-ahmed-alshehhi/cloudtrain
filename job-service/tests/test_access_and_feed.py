"""Members only, and the alert feed the portal reads every 5-10 seconds."""

from tests.conftest import FORM, OTHER, USER, report, submit

OTHER_FORM = {**FORM, "project_id": "project-02", "dataset_id": "dataset-02"}


def test_list_shows_only_that_project(client, check):
    mine = submit(client)["job_id"]
    submit(client, OTHER_FORM, headers=OTHER)

    listed = client.get("/jobs?project_id=project-01", headers=USER).json()

    check(listed, "JobList")
    assert [j["job_id"] for j in listed["items"]] == [mine]


def test_non_members_cannot_see_list_read_cancel_or_follow_a_job(client, check):
    job_id = submit(client)["job_id"]

    for response in (
        client.get("/jobs?project_id=project-01", headers=OTHER),
        client.get(f"/jobs/{job_id}", headers=OTHER),
        client.post(f"/jobs/{job_id}/cancel", headers=OTHER),
        client.get(f"/jobs/{job_id}/events", headers=OTHER),
    ):
        assert response.status_code == 403
        check(response.json(), "Error")
    assert client.get(f"/jobs/{job_id}", headers=USER).json()["status"] == "QUEUED"  # not cancelled


def test_alert_feed_shows_only_my_projects(client):
    submit(client)
    submit(client, OTHER_FORM, headers=OTHER)

    mine = client.get("/jobs/events", headers=USER).json()["items"]
    theirs = client.get("/jobs/events", headers=OTHER).json()["items"]

    assert {e["project_id"] for e in mine} == {"project-01"}
    assert {e["project_id"] for e in theirs} == {"project-02"}


def test_alert_feed_after(client):
    job_id = submit(client)["job_id"]
    first_page = client.get("/jobs/events", headers=USER).json()
    report(client, job_id, "SCHEDULED")

    newer = client.get(f"/jobs/events?after={first_page['last_event_id']}", headers=USER).json()
    nothing_new = client.get(f"/jobs/events?after={newer['last_event_id']}", headers=USER).json()

    assert [e["event_type"] for e in newer["items"]] == ["job.scheduled"]
    assert nothing_new == {"items": [], "last_event_id": newer["last_event_id"]}  # keep your place


def test_alert_feed_limit(client):
    for _ in range(3):
        submit(client)

    page = client.get("/jobs/events?limit=2", headers=USER).json()

    assert len(page["items"]) == 2
    assert page["last_event_id"] == page["items"][-1]["event_id"]


def test_alert_feed_for_a_project_that_is_not_mine_is_403(client, check):
    for project in ("project-02", "project-99"):  # someone else's, and one that does not exist
        response = client.get(f"/jobs/events?project_id={project}", headers=USER)
        assert response.status_code == 403  # the contract allows no 404 here
        check(response.json(), "Error")


def test_job_events_are_oldest_first(client, check):
    job_id = submit(client)["job_id"]
    report(client, job_id, "SCHEDULED")

    found = client.get(f"/jobs/{job_id}/events", headers=USER).json()

    check(found, "EventList")
    assert [e["event_type"] for e in found["items"]] == ["job.queued", "job.scheduled"]
