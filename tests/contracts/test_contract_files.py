"""The files in contracts/ are valid and say what the plan says (run by `make test`)."""

import copy
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
JOB_FORM = json.loads((CONTRACTS / "training-job.schema.json").read_text())
EXAMPLE = JOB_FORM["examples"][0]  # the example from the plan (job-104, ResNet-18, 2-GPU DDP)


def is_valid(form: dict) -> bool:
    return Draft202012Validator(JOB_FORM).is_valid(form)


def test_job_form_accepts_the_plans_example():
    assert is_valid(EXAMPLE)


def broken(change) -> dict:
    form = copy.deepcopy(EXAMPLE)
    change(form)
    return form


@pytest.mark.parametrize(
    "form",
    [
        broken(lambda f: f.pop("dataset_version")),  # our addition: a job trains on a fixed version
        broken(lambda f: f.update(job_id="104")),  # IDs look like job-104
        broken(lambda f: f["parallelism"].update(strategy="tensor")),  # not allowed yet
        broken(lambda f: f["parallelism"].update(strategy="single", world_size=2)),
        broken(lambda f: f["resources"].update(gpu_count=-1)),
        broken(lambda f: f.update(colour="red")),  # unknown fields are refused
    ],
)
def test_job_form_rejects_broken_forms(form):
    assert not is_valid(form)


def test_schemas_and_their_examples_are_valid():
    for name in ["training-job.schema.json", "error-format.json", "events/job-event.schema.json"]:
        schema = json.loads((CONTRACTS / name).read_text())
        Draft202012Validator.check_schema(schema)
        assert all(Draft202012Validator(schema).is_valid(example) for example in schema["examples"]), name


def test_job_submission_is_the_job_form_without_job_id():
    """POST /jobs (job-service.yaml) must stay identical to the shared form, minus job_id."""
    api = yaml.safe_load((CONTRACTS / "openapi" / "job-service.yaml").read_text())
    submission = api["components"]["schemas"]["JobSubmission"]

    assert set(submission["properties"]) == set(JOB_FORM["properties"]) - {"job_id"}
    assert set(submission["required"]) == set(JOB_FORM["required"]) - {"job_id"}


@pytest.mark.parametrize("contract", sorted((CONTRACTS / "openapi").glob("*.yaml")), ids=lambda p: p.name)
def test_every_error_response_uses_the_shared_format(contract):
    api = yaml.safe_load(contract.read_text())
    shared = json.loads((CONTRACTS / "error-format.json").read_text())
    error = api["components"]["schemas"]["Error"]
    assert error["properties"]["error"]["required"] == shared["properties"]["error"]["required"]
    for path, operations in api["paths"].items():
        for method, operation in operations.items():
            for status, answer in operation["responses"].items():
                if not status.startswith("2"):
                    assert "$ref" in answer or "content" not in answer, f"{method.upper()} {path} {status}"
