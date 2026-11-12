# How we work

Every change reaches `main` through a pull request, a passing CI check and a teammate's review.
Nobody pushes to `main` directly.

## The seven steps

1. **Pick your issue** on the board ("CloudTrain" project, linked from the repo's *Projects* tab) and
   drag it to **In progress**. Your issues carry your label (e.g. `s2-faisal`) and a due date.
2. **Create a branch** named `<name>/<short-task>`:
   ```bash
   git switch main && git pull
   git switch -c faisal/upload-checksums
   ```
3. **Commit small changes** with clear messages, e.g. `Add SHA-256 checksum on upload`.
4. **Run `make check`** (lint + unit tests + start everything + contract tests + walk-through).
   It must be green before you open the pull request.
5. **Open a pull request** with `Closes #N` (N = your issue number) and fill in the template.
   Move the card to **In review**.
   ```bash
   git push -u origin faisal/upload-checksums
   gh pr create --fill
   ```
6. **CI runs and a teammate reviews.** The reviewer is requested automatically:
   | Change in... | Reviewer |
   |---|---|
   | a pair's folder (Ahmed + Abdulla, Hamda + Fatma, Hilal + Adel) | the partner |
   | a single owner's folder | the teammate who integrates with it (Faisal→Mariam, Mariam→Maitha, Maitha→Mariam, Abdullah→Ahmed/Abdulla, Majed→Hilal/Adel, Salem→Hamda/Fatma, Ali→Salem) |
   | shared files (`contracts/`, `gateway/`, `docker-compose.yml`, `Makefile`, `local/`, `tests/`, `docs/ARCHITECTURE.md`, `team.yml`, `.github/`) | **Ali must also approve** (CODEOWNERS) |

   Fix what the reviewer asks, push again, and CI runs again.
7. **Merge.** The issue closes itself (thanks to `Closes #N`) and moves to **Done**.

## Rules on `main` (set by `scripts/protect_main.sh`)
- pull request required, no direct pushes, no force-push
- 1 approval from someone other than the author (+ Ali for shared files)
- CI must pass, on a branch that is up to date with `main`

## Changing a contract
Anything in `contracts/`, ports, gateway routes, queue readers, shared rules or `docker-compose.yml`:
open a **Contract change** issue, tag Ali and the affected owners, agree, change `contracts/` **first**
(its own pull request), then the code, then add a file to `docs/decisions/`.

## When you are blocked
Add the `blocked` label to your issue and say in a comment who you are waiting for. Keep working with
the stand-in. Mention it at the daily 15-minute check-in.

## Getting notified
- Install the **GitHub mobile app** and sign in.
- On the repo page: **Watch → Custom → tick Issues and Pull requests → Apply**.
  (Ali watches everything, so he sees every pull request.)
- GitHub also notifies you when you are assigned an issue, asked to review, or `@mentioned`.

## The board columns
**To do** → **In progress** (you started) → **In review** (pull request open) → **Done** (merged).
If GitHub does not move a card by itself, drag it.
