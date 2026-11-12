#!/bin/bash
# Protect the `main` branch on GitHub, so every change goes through a reviewed, tested pull request:
#   - a pull request is required (no direct pushes)
#   - 1 approval from someone other than the author
#   - code-owner review: changes to the shared files in .github/CODEOWNERS need Ali's approval
#   - the CI check ("checks" in .github/workflows/ci.yml) must pass, on a branch that is up to date
#   - no force-push, no deleting main
# Usage: bash scripts/protect_main.sh          (needs `gh`, logged in as the repository owner)
set -euo pipefail

repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
echo "Protecting main on $repo ..."

# enforce_admins is false on purpose: Ali is the only code owner, and GitHub never lets authors
# approve their own pull requests. Without this, Ali could never merge his own changes to shared
# files. Ali still asks a teammate to review them (the reviewer workflow requests Salem).
if gh api --method PUT "repos/$repo/branches/main/protection" --input - >/dev/null <<'JSON'
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "checks" } ] },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
then
  echo "Done. main now needs: a pull request, 1 approval (+ Ali for shared files), green CI, up to date."
  echo "Check it on GitHub: Settings -> Branches."
else
  cat <<'HELP'

Could not protect main. The usual reasons:
  - The repository is PRIVATE on a free GitHub account: protection needs a public repository
    or GitHub Pro / Team (see docs/decisions/0004-public-repository.md).
  - You are not logged in as the owner: run `gh auth status`.

To do it by hand on GitHub: Settings -> Branches -> Add branch protection rule -> pattern "main", tick:
  [x] Require a pull request before merging
      [x] Require approvals: 1
      [x] Dismiss stale pull request approvals when new commits are pushed
      [x] Require review from Code Owners
  [x] Require status checks to pass before merging
      [x] Require branches to be up to date before merging
      Status check: "checks"
  Leave "Do not allow bypassing the above settings" UNticked (Ali is the only code owner).
  Force pushes and deletions stay blocked (the default).
HELP
  exit 1
fi
