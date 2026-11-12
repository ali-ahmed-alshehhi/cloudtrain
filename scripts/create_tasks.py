"""Create the team's GitHub tracking from team.yml and scripts/team_plan.yml:
collaborator invitations, labels, milestones, the "CloudTrain" project board, one issue per row of
each person's dated plan, and one issue per hand-off.

    bash scripts/create_tasks.sh            # DRY RUN: only prints what it would do
    bash scripts/create_tasks.sh --apply    # really does it

Safe to run again: existing labels, milestones, issues and board cards are reused, never duplicated.
Run it again after the GitHub usernames in team.yml are filled in (and the invitations accepted):
it then assigns the issues to their owners. Needs the GitHub CLI (`gh`) logged in with the
`project` permission (`gh auth refresh -s project`).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOARD_TITLE = "CloudTrain"
BOARD_COLUMNS = [  # (name, colour, meaning)
    ("To do", "GRAY", "Not started"),
    ("In progress", "YELLOW", "Being worked on"),
    ("In review", "BLUE", "Pull request open, waiting for review"),
    ("Done", "GREEN", "Merged / finished"),
]
DUE_FIELD = "Due"
EXTRA_LABELS = {  # name: (colour, description)
    "contract-change": (
        "d93f0b",
        "Changes contracts/, ports, routes or shared rules: needs Ali and the affected owners",
    ),
    "blocked": ("b60205", "Waiting on someone else; say who in a comment"),
    "hand-off": ("5319e7", "One person delivers something another person needs"),
}
PHASE_COLOUR = "0e8a16"
PERSON_COLOUR = "1d76db"


class GhError(Exception):
    pass


def gh(*args: str, stdin: str | None = None) -> str:
    """Run one GitHub CLI command and return what it printed."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin)
    if result.returncode != 0:
        raise GhError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


# ---------- reading the plan ----------


class Student:
    def __init__(self, number: int, data: dict) -> None:
        self.number = number
        self.names: list[str] = data["names"]
        self.logins = [login for login in data["github"] if login and not str(login).startswith("FILL_ME")]
        self.role: str = data["role"]

    @property
    def title(self) -> str:
        return " + ".join(self.names)

    @property
    def label(self) -> str:
        return f"s{self.number}-" + "-".join(name.lower() for name in self.names)

    def mention(self) -> str:
        """@login if known (GitHub then notifies them), otherwise just the name."""
        return " ".join(f"@{login}" for login in self.logins) if self.logins else self.title


def load_plan() -> tuple[dict[int, Student], dict, str | None]:
    team = yaml.safe_load((ROOT / "team.yml").read_text())
    plan = yaml.safe_load((ROOT / "scripts" / "team_plan.yml").read_text())
    students = {int(number): Student(int(number), data) for number, data in team["students"].items()}
    repo_url = team.get("repo", "")
    repo = None if repo_url.startswith("FILL_ME") else repo_url.removeprefix("https://github.com/").strip("/")
    return students, plan, repo


def first_on_or_after(items: list[dict], key: str, due) -> dict:
    return next(item for item in items if item[key] >= due)


def who(value, students: dict[int, Student]) -> list[Student]:
    """[2, 3] -> those students; "everyone" -> all; "instructors" -> nobody on GitHub."""
    if value == "everyone":
        return list(students.values())
    if value == "instructors":
        return []
    return [students[number] for number in value]


# ---------- what to create ----------


def task_issue(row: dict, students: dict[int, Student], plan: dict, repo: str) -> dict:
    student = students[row["student"]]
    short = row["task"].split(". ")[0].rstrip(".")
    short = short if len(short) <= 70 else short[:67] + "..."
    links = plan["links"][row["student"]]
    folder_links = "\n".join(
        f"- Your folder: [{folder}/README.md](https://github.com/{repo}/blob/main/{folder}/README.md)"
        for folder in links["folders"]
    )
    contract_links = "\n".join(
        f"- Contract: [{path}](https://github.com/{repo}/blob/main/{path})" for path in links["contracts"]
    )
    body = f"""## Task
{row["task"]}

**When:** {row["dates"]} (due {row["due"]:%a %d %b})
**Owner:** {student.mention()} — Student {student.number}, {student.role}
**Waiting on:** {row["waiting_on"]}

## Definition of done
- [ ] The work above is done and matches the contract in `contracts/`
- [ ] `/health` and `/metrics` still work; errors use the shared error format
- [ ] Tests added for the main path and at least one failure path
- [ ] `make check` passes
- [ ] README updated
- [ ] Merged through a pull request that says "Closes #<this issue number>"

## Links
{folder_links}
{contract_links}
- How we work: [docs/TEAM_WORKFLOW.md](https://github.com/{repo}/blob/main/docs/TEAM_WORKFLOW.md)
- Your guide: [TEAM_GUIDE.md](https://github.com/{repo}/blob/main/TEAM_GUIDE.md)
"""
    return {
        "title": f"[S{student.number} {student.title}] {row['dates']}: {short}",
        "body": body,
        "labels": [student.label, phase_of(row["due"], plan)],
        "milestone": first_on_or_after(plan["milestones"], "due", row["due"])["title"],
        "assignees": student.logins,
        "due": row["due"],
    }


def handoff_issue(row: dict, students: dict[int, Student], plan: dict) -> dict:
    givers, receivers = who(row["from"], students), who(row["to"], students)
    giver_text = (
        "Everyone"
        if row["from"] == "everyone"
        else ("Instructors" if not givers else " + ".join(s.title for s in givers))
    )
    receiver_text = "Everyone" if row["to"] == "everyone" else " + ".join(s.title for s in receivers)
    # Assigned to the giver. When the giver is everyone or the instructors, the receivers follow it up.
    owners = receivers if row["from"] in ("everyone", "instructors") else givers
    body = f"""## Hand-off
**What:** {row["what"]}
**From:** {" ".join(s.mention() for s in givers) or giver_text}
**To:** {" ".join(s.mention() for s in receivers) if row["to"] != "everyone" else "everyone"}
**Due:** {row["due"]:%a %d %b}

If this is late, the receiver keeps working with the stand-in and the giver tells the group the
same day. Close this issue when the receiver confirms it works for them.
"""
    return {
        "title": f"[Hand-off {row['date']}] {giver_text} → {receiver_text}: {row['what']}",
        "body": body,
        "labels": ["hand-off", phase_of(row["due"], plan), *[s.label for s in givers]],
        "milestone": first_on_or_after(plan["milestones"], "due", row["due"])["title"],
        "assignees": [login for s in owners for login in s.logins][:10],  # GitHub allows 10 assignees
        "due": row["due"],
    }


def phase_of(due, plan: dict) -> str:
    return first_on_or_after(plan["phases"], "until", due)["label"]


# ---------- doing it ----------


class Tracker:
    def __init__(self, repo: str, apply: bool) -> None:
        self.repo = repo
        self.owner = repo.split("/")[0]
        self.apply = apply
        self.warnings: list[str] = []
        self.repo_exists = self._repo_exists()

    def _repo_exists(self) -> bool:
        try:
            gh("repo", "view", self.repo, "--json", "name")
            return True
        except GhError:
            if self.apply:
                sys.exit(
                    f"The repository {self.repo} does not exist on GitHub yet. Create and push it first."
                )
            print(f"(The repository {self.repo} does not exist yet: showing everything as new.)\n")
            return False

    def act(self, description: str, *command: str, stdin: str | None = None) -> str:
        print(("  " if self.apply else "  would: ") + description)
        return gh(*command, stdin=stdin) if self.apply else ""

    # -- people --
    def invite(self, students: dict[int, Student]) -> None:
        print("Collaborators (write access, so they can push branches and be assigned):")
        for student in students.values():
            for login in student.logins:
                if login.lower() == self.owner.lower():
                    continue
                try:
                    self.act(
                        f"invite {login} ({student.title})",
                        "api",
                        "-X",
                        "PUT",
                        f"repos/{self.repo}/collaborators/{login}",
                        "-f",
                        "permission=push",
                    )
                except GhError as error:
                    self.warnings.append(f"Could not invite {login}: {error}")
        missing = [s.title for s in students.values() if not s.logins or len(s.logins) < len(s.names)]
        if missing:
            self.warnings.append(
                "No GitHub username yet in team.yml for: "
                + ", ".join(missing)
                + ". Their issues stay unassigned until you fill them in and run this again."
            )

    # -- labels and milestones --
    def labels(self, students: dict[int, Student], plan: dict) -> None:
        print("Labels:")
        wanted = {s.label: (PERSON_COLOUR, f"Student {s.number}: {s.role}") for s in students.values()}
        wanted |= {p["label"]: (PHASE_COLOUR, f"Phase, due by {p['until']:%a %d %b}") for p in plan["phases"]}
        wanted |= EXTRA_LABELS
        for name, (colour, description) in wanted.items():
            self.act(
                f"label {name}",
                "label",
                "create",
                name,
                "--repo",
                self.repo,
                "--color",
                colour,
                "--description",
                description,
                "--force",
            )

    def milestones(self, plan: dict) -> None:
        print("Milestones:")
        existing = set()
        if self.repo_exists:
            listed = json.loads(gh("api", f"repos/{self.repo}/milestones?state=all&per_page=100"))
            existing = {m["title"] for m in listed}
        for milestone in plan["milestones"]:
            if milestone["title"] in existing:
                print(f"  exists: {milestone['title']}")
                continue
            self.act(
                f"milestone {milestone['title']} (due {milestone['due']:%a %d %b})",
                "api",
                "-X",
                "POST",
                f"repos/{self.repo}/milestones",
                "-f",
                f"title={milestone['title']}",
                "-f",
                f"due_on={milestone['due']}T23:59:59Z",
                "-f",
                f"description={milestone['description']}",
            )

    # -- the board --
    def board(self) -> dict | None:
        """Find or create the project board; returns its ids, or None in a dry run without one."""
        print("Project board:")
        projects = json.loads(
            gh("project", "list", "--owner", self.owner, "--format", "json", "--limit", "100")
        )
        found = next((p for p in projects["projects"] if p["title"] == BOARD_TITLE), None)
        if found is None:
            created = self.act(
                f"create project board '{BOARD_TITLE}'",
                "project",
                "create",
                "--owner",
                self.owner,
                "--title",
                BOARD_TITLE,
                "--format",
                "json",
            )
            if not self.apply:
                print(
                    f"  would: set its columns to {', '.join(c[0] for c in BOARD_COLUMNS)} and add a "
                    f"'{DUE_FIELD}' date field"
                )
                return None
            found = json.loads(created)
        else:
            print(f"  exists: {BOARD_TITLE} (#{found['number']})")
        number = str(found["number"])
        try:
            self.act(
                f"link the board to {self.repo}",
                "project",
                "link",
                number,
                "--owner",
                self.owner,
                "--repo",
                self.repo,
            )
        except GhError:
            pass  # already linked
        fields = json.loads(gh("project", "field-list", number, "--owner", self.owner, "--format", "json"))[
            "fields"
        ]
        status = next(f for f in fields if f["name"] == "Status")
        if [o["name"] for o in status.get("options", [])] != [c[0] for c in BOARD_COLUMNS]:
            self._set_columns(status["id"])
            fields = json.loads(
                gh("project", "field-list", number, "--owner", self.owner, "--format", "json")
            )["fields"]
            status = next(f for f in fields if f["name"] == "Status")
        if not any(f["name"] == DUE_FIELD for f in fields):
            self.act(
                f"add the '{DUE_FIELD}' date field",
                "project",
                "field-create",
                number,
                "--owner",
                self.owner,
                "--name",
                DUE_FIELD,
                "--data-type",
                "DATE",
            )
            fields = json.loads(
                gh("project", "field-list", number, "--owner", self.owner, "--format", "json")
            )["fields"]
        project_id = json.loads(gh("project", "view", number, "--owner", self.owner, "--format", "json"))[
            "id"
        ]
        return {
            "number": number,
            "id": project_id,
            "status_field": status["id"],
            "to_do": next(o["id"] for o in status["options"] if o["name"] == BOARD_COLUMNS[0][0]),
            "due_field": next(f["id"] for f in fields if f["name"] == DUE_FIELD),
            "on_board": self._issues_on_board(number),
        }

    def _issues_on_board(self, number: str) -> set[str]:
        """Addresses of the issues already on the board, so a re-run does not touch them again."""
        listed = gh(
            "project", "item-list", number, "--owner", self.owner, "--format", "json", "--limit", "1000"
        )
        return {item.get("content", {}).get("url") for item in json.loads(listed)["items"]}

    def _set_columns(self, field_id: str) -> None:
        query = """mutation($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
          updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) { clientMutationId }
        }"""
        options = [{"name": n, "color": c, "description": d} for n, c, d in BOARD_COLUMNS]
        body = json.dumps({"query": query, "variables": {"field": field_id, "options": options}})
        self.act(
            "set the board columns: " + ", ".join(c[0] for c in BOARD_COLUMNS),
            "api",
            "graphql",
            "--input",
            "-",
            stdin=body,
        )

    # -- issues --
    def issues(self, wanted: list[dict], board: dict | None) -> None:
        print(f"Issues ({len(wanted)}):")
        existing = {}
        if self.repo_exists:
            listed = json.loads(
                gh(
                    "issue",
                    "list",
                    "--repo",
                    self.repo,
                    "--state",
                    "all",
                    "--limit",
                    "500",
                    "--json",
                    "number,title,url,assignees",
                )
            )
            existing = {issue["title"]: issue for issue in listed}
        for issue in wanted:
            found = existing.get(issue["title"])
            if found:
                assigned = {a["login"].lower() for a in found["assignees"]}
                missing = [login for login in issue["assignees"] if login.lower() not in assigned]
                if missing:
                    self._try(
                        f"assign #{found['number']} to {', '.join(missing)}",
                        "issue",
                        "edit",
                        str(found["number"]),
                        "--repo",
                        self.repo,
                        *sum((["--add-assignee", m] for m in missing), []),
                    )
                url, new = found["url"], False
            else:
                url, new = self._create(issue), True
            if board and url and url not in board["on_board"]:  # cards already there are left alone
                self._put_on_board(board, url, issue["due"], new)

    def _create(self, issue: dict) -> str:
        command = [
            "issue",
            "create",
            "--repo",
            self.repo,
            "--title",
            issue["title"],
            "--body-file",
            "-",
            "--milestone",
            issue["milestone"],
            *sum((["--label", label] for label in issue["labels"]), []),
        ]
        assignees = ["--assignee", ",".join(issue["assignees"])] if issue["assignees"] else []
        who_text = f" -> {', '.join(issue['assignees'])}" if issue["assignees"] else " (unassigned)"
        try:
            return self.act(
                f"issue {issue['title']}{who_text}", *command, *assignees, stdin=issue["body"]
            ).strip()
        except GhError as error:
            if not assignees:
                raise
            # Usually: the person has not accepted the collaborator invitation yet.
            self.warnings.append(
                f"Created unassigned (run again later to assign): {issue['title']} — {error}"
            )
            return gh(*command, stdin=issue["body"]).strip()

    def _put_on_board(self, board: dict, url: str, due, new: bool) -> None:
        item = json.loads(
            gh(
                "project",
                "item-add",
                board["number"],
                "--owner",
                self.owner,
                "--url",
                url,
                "--format",
                "json",
            )
        )
        gh(
            "project",
            "item-edit",
            "--project-id",
            board["id"],
            "--id",
            item["id"],
            "--field-id",
            board["due_field"],
            "--date",
            str(due),
        )
        if new:  # only new cards start in "To do"; never move an existing card back
            gh(
                "project",
                "item-edit",
                "--project-id",
                board["id"],
                "--id",
                item["id"],
                "--field-id",
                board["status_field"],
                "--single-select-option-id",
                board["to_do"],
            )

    def _try(self, description: str, *command: str) -> None:
        try:
            self.act(description, *command)
        except GhError as error:
            self.warnings.append(f"{description}: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="really create things (default: dry run)")
    parser.add_argument("--repo", help="owner/name (default: the repo in team.yml)")
    args = parser.parse_args()

    students, plan, repo_from_team = load_plan()
    repo = args.repo or repo_from_team
    if not repo:
        sys.exit(
            "Set `repo:` in team.yml (e.g. https://github.com/owner/cloudtrain) or pass --repo owner/name."
        )
    print(
        f"{'CREATING' if args.apply else 'DRY RUN (nothing is changed; add --apply to do it)'} for {repo}\n"
    )

    tracker = Tracker(repo, args.apply)
    tasks = [task_issue(row, students, plan, repo) for row in plan["tasks"]]
    handoffs = [handoff_issue(row, students, plan) for row in plan["handoffs"]]

    tracker.invite(students)
    tracker.labels(students, plan)
    tracker.milestones(plan)
    board = tracker.board()
    tracker.issues(tasks + handoffs, board)

    print(
        f"\nSummary: {len(tasks)} task issues, {len(handoffs)} hand-off issues, "
        f"{sum(1 for i in tasks + handoffs if i['assignees'])} of them with an owner on GitHub."
    )
    for warning in tracker.warnings:
        print("WARNING:", warning)


if __name__ == "__main__":
    main()
