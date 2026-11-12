# 0004 — Public GitHub repository

- **Status:** proposed — waiting for the instructors (Manzoor, Asif) to confirm a public repo is allowed
- **Date:** 2026-11-12
- **Decided by:** Ali

## Context
We need branch protection on `main` (pull request, review and green CI before merging). On a free GitHub
account, protection rules do not work on private repositories.

Options considered:
1. A public repository.
2. A private repository on GitHub Pro (free through the GitHub Student Developer Pack).
3. A GitHub organisation on a plan that supports protection.

## Decision
Option 1: a public repository.

## Why
Fastest to set up before the team starts on Sat 14 Nov, with no account upgrade to wait for.
It is safe because no secrets are ever committed (`.env` and Terraform state are git-ignored; only
`.env.example` with fake values is in the repo; CI scans for secrets).

## Trade-offs
Anyone can read the code. If the instructors say no, switch to option 2; only `scripts/protect_main.sh`
is affected.
