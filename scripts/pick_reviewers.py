"""Pick who reviews a pull request. Used by .github/workflows/assign-reviewers.yml.

    python scripts/pick_reviewers.py AUTHOR CHANGED_FILE [CHANGED_FILE ...]

Prints GitHub usernames separated by commas (or nothing). The rules (docs/TEAM_WORKFLOW.md):
  - a change in a PAIR's folder: the partner reviews
  - a change in a SINGLE owner's folder: a teammate who integrates with that service
    (from the dependency table in docs/ARCHITECTURE.md)
  - Ali only if nobody else fits
Changes to shared files (contracts/, gateway/, docker-compose.yml, ...) ALSO need Ali's approval:
GitHub adds him automatically through .github/CODEOWNERS.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALI = 1

# Single-owner student -> the student who reviews their work (they integrate with each other).
INTEGRATION_REVIEWER = {
    1: 9,  # Ali (gateway, projects)      -> Salem (real login lives in the gateway)
    2: 3,  # Faisal (datasets)            -> Mariam (checks dataset versions before accepting jobs)
    3: 7,  # Mariam (training jobs)       -> Maitha (reads the queue, reports job status)
    4: 5,  # Abdullah (training runtime)  -> Ahmed + Abdulla (DDP is built on it)
    7: 3,  # Maitha (scheduler)           -> Mariam
    8: 10,  # Majed (registry, inference) -> Hilal + Adel (models and prediction pages)
    9: 6,  # Salem (CI/CD, security)      -> Hamda + Fatma (IAM, deployment)
}


def known_logins(student: dict) -> list[str]:
    return [login for login in student["github"] if login and not str(login).startswith("FILL_ME")]


def owner_of(path: str, folders: dict[str, int]) -> int | None:
    """The student whose folder holds this file. The longest match wins
    (training/distributed beats training)."""
    matches = [folder for folder in folders if path == folder or path.startswith(folder.rstrip("/") + "/")]
    return folders[max(matches, key=len)] if matches else None


def pick(author: str, changed_files: list[str], students: dict[int, dict]) -> list[str]:
    folders = {folder: number for number, s in students.items() for folder in s["folders"]}
    author = author.lower()
    reviewers: list[str] = []

    def add(student_number: int, how_many: int | None = None) -> None:
        candidates = [login for login in known_logins(students[student_number]) if login.lower() != author]
        for login in candidates[:how_many]:
            if login not in reviewers:
                reviewers.append(login)

    for owner in {owner_of(path, folders) for path in changed_files} - {None}:
        team = students[owner]
        is_pair = len(team["names"]) > 1
        author_is_owner = author in (login.lower() for login in known_logins(team))
        if is_pair and author_is_owner:
            add(owner)  # the partner
        elif is_pair:
            add(owner, how_many=1)  # someone changed a pair's folder: one of the pair reviews
        elif author_is_owner:
            add(INTEGRATION_REVIEWER.get(owner, ALI), how_many=1)
        else:
            add(owner)  # someone changed a single owner's folder: that owner reviews

    if not reviewers:  # nothing fitted: Ali, or Salem when Ali is the author
        add(ALI)
        if not reviewers:
            add(INTEGRATION_REVIEWER[ALI], how_many=1)
    return reviewers


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    team = yaml.safe_load((ROOT / "team.yml").read_text())
    students = {int(number): data for number, data in team["students"].items()}
    print(",".join(pick(sys.argv[1], sys.argv[2:], students)))


if __name__ == "__main__":
    main()
