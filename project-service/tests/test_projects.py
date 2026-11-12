"""The Projects service keeps its contract: create, list, read, members, who am I."""

import pytest

from tests.conftest import ALICE, BOB, create

# ---------- create ----------


def test_create_project(client, check):
    response = client.post(
        "/projects",
        json={"name": "Image Classification", "description": "CIFAR-10 with ResNet-18"},
        headers=ALICE,
    )

    assert response.status_code == 201
    project = response.json()
    check(project, "Project")
    assert project["project_id"] == "project-01"
    assert project["owner_id"] == "user-alice"
    assert [(m["user_id"], m["role"]) for m in project["members"]] == [("user-alice", "owner")]
    assert project["created_at"].endswith("Z")


def test_project_ids_count_up(client):
    assert create(client)["project_id"] == "project-01"
    assert create(client, name="Tabular")["project_id"] == "project-02"


def test_create_without_login_is_401(client, check):
    response = client.post("/projects", json={"name": "x"})

    assert response.status_code == 401
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.parametrize(
    "body",
    [{}, {"name": ""}, {"name": "x" * 101}, {"name": "ok", "colour": "red"}, {"name": 5}],
)
def test_create_with_bad_body_is_422(client, check, body):
    response = client.post("/projects", json=body, headers=ALICE)

    assert response.status_code == 422
    check(response.json(), "Error")


def test_create_with_broken_json_is_422(client, check):
    response = client.post(
        "/projects", content=b"{not json", headers={**ALICE, "Content-Type": "application/json"}
    )

    assert response.status_code == 422
    check(response.json(), "Error")


# ---------- idempotency ----------


def test_same_idempotency_key_creates_only_once(client):
    first = create(client, **{"Idempotency-Key": "key-1"})
    second = create(client, **{"Idempotency-Key": "key-1"})

    assert first == second
    assert len(client.get("/projects", headers=ALICE).json()["items"]) == 1


def test_idempotency_key_reused_for_another_request_is_409(client, check):
    create(client, **{"Idempotency-Key": "key-1"})

    response = client.post(
        "/projects", json={"name": "Different"}, headers={**ALICE, "Idempotency-Key": "key-1"}
    )

    assert response.status_code == 409
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_idempotency_keys_belong_to_one_user(client):
    alice_project = create(client, headers=ALICE, **{"Idempotency-Key": "same"})
    bob_project = create(client, headers=BOB, **{"Idempotency-Key": "same"})

    assert alice_project["project_id"] != bob_project["project_id"]


# ---------- list and read ----------


def test_list_shows_only_my_projects(client, check):
    create(client, name="Alice's", headers=ALICE)
    create(client, name="Bob's", headers=BOB)

    response = client.get("/projects", headers=ALICE)

    assert response.status_code == 200
    check(response.json(), "ProjectList")
    assert [p["name"] for p in response.json()["items"]] == ["Alice's"]


def test_member_can_read_project(client, check):
    project = create(client)

    response = client.get(f"/projects/{project['project_id']}", headers=ALICE)

    assert response.status_code == 200
    check(response.json(), "Project")


def test_non_member_gets_403(client, check):
    project = create(client)

    response = client.get(f"/projects/{project['project_id']}", headers=BOB)

    assert response.status_code == 403
    check(response.json(), "Error")
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"


def test_missing_project_is_404(client, check):
    response = client.get("/projects/project-99", headers=ALICE)

    assert response.status_code == 404
    check(response.json(), "Error")


def test_badly_formed_project_id_is_422(client, check):
    response = client.get("/projects/dataset-01", headers=ALICE)

    assert response.status_code == 422
    check(response.json(), "Error")


# ---------- members ----------


def test_owner_adds_a_member_who_can_then_read(client, check):
    project_id = create(client)["project_id"]

    response = client.post(f"/projects/{project_id}/members", json={"user_id": "user-bob"}, headers=ALICE)

    assert response.status_code == 201
    check(response.json(), "Member")
    assert response.json()["role"] == "member"
    assert client.get(f"/projects/{project_id}", headers=BOB).status_code == 200


def test_plain_member_cannot_add_members(client):
    project_id = create(client)["project_id"]
    client.post(f"/projects/{project_id}/members", json={"user_id": "user-bob"}, headers=ALICE)

    response = client.post(f"/projects/{project_id}/members", json={"user_id": "user-carol"}, headers=BOB)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_PROJECT_OWNER"


def test_stranger_cannot_add_members(client):
    project_id = create(client)["project_id"]

    response = client.post(f"/projects/{project_id}/members", json={"user_id": "user-bob"}, headers=BOB)

    assert response.status_code == 403


def test_adding_an_existing_member_is_409(client, check):
    project_id = create(client)["project_id"]
    client.post(f"/projects/{project_id}/members", json={"user_id": "user-bob"}, headers=ALICE)

    response = client.post(f"/projects/{project_id}/members", json={"user_id": "user-bob"}, headers=ALICE)

    assert response.status_code == 409
    check(response.json(), "Error")


def test_adding_member_to_missing_project_is_404(client):
    response = client.post("/projects/project-42/members", json={"user_id": "user-bob"}, headers=ALICE)

    assert response.status_code == 404


def test_adding_a_member_twice_with_the_same_key_is_not_an_error(client):
    project_id = create(client)["project_id"]
    headers = {**ALICE, "Idempotency-Key": "add-bob"}

    first = client.post(f"/projects/{project_id}/members", json={"user_id": "user-bob"}, headers=headers)
    second = client.post(f"/projects/{project_id}/members", json={"user_id": "user-bob"}, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()


# ---------- who am I ----------


def test_users_me_lists_my_projects(client, check):
    first = create(client)["project_id"]
    create(client, headers=BOB)
    third = create(client, name="Tabular")["project_id"]

    response = client.get("/users/me", headers=ALICE)

    assert response.status_code == 200
    check(response.json(), "User")
    assert response.json() == {"user_id": "user-alice", "project_ids": [first, third]}
