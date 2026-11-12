"""The reviewer rules of .github/workflows/assign-reviewers.yml (scripts/pick_reviewers.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from pick_reviewers import pick  # noqa: E402

# A pretend team with every GitHub username filled in.
STUDENTS = {
    1: {"names": ["Ali"], "github": ["ali"], "folders": ["gateway", "project-service", "contracts"]},
    2: {"names": ["Faisal"], "github": ["faisal"], "folders": ["dataset-service"]},
    3: {"names": ["Mariam"], "github": ["mariam"], "folders": ["job-service", "contracts/events"]},
    4: {"names": ["Abdullah"], "github": ["abdullah"], "folders": ["training", "mlflow"]},
    5: {"names": ["Ahmed", "Abdulla"], "github": ["ahmed", "abdulla"], "folders": ["training/distributed"]},
    6: {"names": ["Hamda", "Fatma"], "github": ["hamda", "fatma"], "folders": ["infrastructure"]},
    7: {"names": ["Maitha"], "github": ["maitha"], "folders": ["scheduler"]},
    8: {"names": ["Majed"], "github": ["majed"], "folders": ["model-registry", "inference-service"]},
    9: {"names": ["Salem"], "github": ["salem"], "folders": [".github/workflows", "security"]},
    10: {"names": ["Hilal", "Adel"], "github": ["hilal", "adel"], "folders": ["portal"]},
}


@pytest.mark.parametrize(
    ("author", "files", "expected"),
    [
        ("faisal", ["dataset-service/app/main.py"], ["mariam"]),  # single owner -> integrating teammate
        ("ahmed", ["training/distributed/ddp.py"], ["abdulla"]),  # pair -> partner (longest folder wins)
        ("hamda", ["infrastructure/main.tf"], ["fatma"]),
        ("mariam", ["job-service/app/main.py", "contracts/events/x.json"], ["maitha"]),
        ("ali", ["contracts/openapi/job-service.yaml"], ["salem"]),  # CODEOWNERS adds Ali's approval need
        ("majed", ["inference-service/app/main.py"], ["hilal"]),
        ("abdullah", ["dataset-service/app/main.py"], ["faisal"]),  # someone else's folder -> its owner
        ("hilal", ["README.md"], ["ali"]),  # nobody owns it -> Ali
        ("ali", ["README.md"], ["salem"]),  # ...unless Ali wrote it
    ],
)
def test_reviewer_rules(author, files, expected):
    assert pick(author, files, STUDENTS) == expected


def test_unknown_usernames_are_skipped():
    team = {**STUDENTS, 3: {**STUDENTS[3], "github": ["FILL_ME"]}}

    assert pick("faisal", ["dataset-service/app/main.py"], team) == ["ali"]  # Mariam unknown -> Ali
