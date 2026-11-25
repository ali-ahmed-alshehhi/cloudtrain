# Test I: the whole website, end to end (raw results)

**Measured:** Wed 25 Nov 2026, about 13:05 (UTC+4), by Adel on the laptop in section 0 of `EVALUATION.md`.
**Versions:** `main` at `cf9a6b7`: every portal page is on `main` (Hilal's #99 and #165, Adel's #156 and #160).
Normal settings. Browser: the laptop's Google Chrome, headless (Playwright).
**Question:** with every team's part on `main`, does the website work end to end, through the gateway only?

**Note on the build.** `make up` (`docker compose up --build`) failed once: the base image `python:3.11-slim`
had changed upstream, so every image was rebuilt from scratch; the training worker downloads about 3 GB
(PyTorch with its NVIDIA libraries) and one of those files (`nvidia_cudnn`, 595 MB) broke off halfway
(329.8 MB) on the campus network, so pip refused it (hash mismatch). The other 10 images built. The stack was
then started without rebuilding (`docker compose up --detach --wait`), with the training worker image built on
23 Nov; the training worker's code has not changed since then (`git log 2239c22..cf9a6b7 -- training/` is
empty).

## Commands and output

```bash
docker compose up --detach --wait       # make up without --build (see the note)
make e2e
cd portal
export PLAYWRIGHT_CHROME_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
npm ci
npm run test:e2e                        # all six browser tests in portal/tests/e2e/
```

```
adilaldashti@Adils-MacBook-Pro cloudtrain % docker compose up --detach --wait
[+] up 15/15
 ✔ Container cloudtrain-job-events-monitor-1 Healthy                                                             33.1s
 ✔ Container cloudtrain-model-registry-1     Healthy                                                             30.1s
 ✔ Container cloudtrain-project-service-1    Healthy                                                             30.1s
 ✔ Container cloudtrain-dataset-service-1    Healthy                                                             29.8s
 ✔ Container cloudtrain-inference-service-1  Healthy                                                             29.8s
 ✔ Container cloudtrain-job-service-1        Healthy                                                             29.6s
 ✔ Container cloudtrain-scheduler-1          Healthy                                                             33.4s
 ✔ Container cloudtrain-gateway-1            Healthy                                                             28.9s
 ✔ Container cloudtrain-portal-1             Healthy                                                             33.8s
 ✔ Container cloudtrain-prometheus-1         Healthy                                                             28.6s
 ✔ Container cloudtrain-postgres-1           Healthy                                                             28.6s
 ✔ Container cloudtrain-localstack-1         Healthy                                                             28.6s
 ✔ Container cloudtrain-grafana-1            Healthy                                                             23.0s
 ✔ Container cloudtrain-mlflow-1             Healthy                                                             22.9s
 ✔ Container cloudtrain-training-worker-1    Healthy                                                              6.3s
adilaldashti@Adils-MacBook-Pro cloudtrain % make e2e
.venv/bin/python -m pytest tests/integration -q -p no:warnings -rs  # -rs: list skipped steps and their owners
s..............s.......ss....                                                                                  [100%]
============================================== short test summary info ===============================================
SKIPPED [1] tests/integration/test_failure_recovery.py:29: needs short heartbeat settings (HEARTBEAT_TIMEOUT_SECONDS<=30), as in CI: see the docstring
SKIPPED [1] tests/integration/test_walkthrough.py:81: `make up` uses the dev token; `make e2e-login` runs this step with the real login
SKIPPED [1] tests/integration/test_walkthrough.py:176: Maitha: the machine is released after the job — Fri 20 Nov
SKIPPED [1] tests/integration/test_walkthrough.py:184: Hilal + Adel; Ahmed + Abdulla: single-GPU vs DDP comparison — Tue 24 Nov
25 passed, 4 skipped in 21.27s
adilaldashti@Adils-MacBook-Pro cloudtrain % cd portal
adilaldashti@Adils-MacBook-Pro portal % export PLAYWRIGHT_CHROME_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
adilaldashti@Adils-MacBook-Pro portal % npm ci

added 25 packages, and audited 26 packages in 2s

6 packages are looking for funding
  run `npm fund` for details

found 0 vulnerabilities
npm warn install-scripts 1 package has install scripts not yet covered by allowScripts:
npm warn install-scripts   fsevents@2.3.2 (install: (install scripts present))
npm warn install-scripts
npm warn install-scripts Run `npm install-scripts ls` to review, or `npm install-scripts approve <pkg>` to allow.
adilaldashti@Adils-MacBook-Pro portal % npm run test:e2e

> cloudtrain-portal@0.1.0 test:e2e
> node --test tests/e2e/*.test.cjs

Verified dataset-87: real CSV uploads, versions 1/2, retry idempotency and project isolation.
✔ datasets: live uploads, validation, retry, versions and project isolation (3789.046083ms)
Live browser job passed: http://localhost:3000/jobs/job-51
✔ live CPU job: choose version, submit, history and MLflow results through the browser (7711.248375ms)
✔ job form and detail: exact version, safe retry, live history, cancellation and project isolation (2405.20425ms)
✔ compare and usage pages: project in the address, honest results, gateway only (2407.371084ms)
Verified project project-83 through the live gateway.
✔ projects: create, refresh, select, validate and recover from a network error (2451.0785ms)
✔ pending dataset and version uploads keep project and retry identity alive (2731.733209ms)
ℹ tests 6
ℹ suites 0
ℹ pass 6
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 8640.247708
```

## Summary

| Check | Result |
|---|---|
| All containers | **15 of 15 healthy** |
| Walk-through through the gateway (`make e2e`) | **25 passed**, 4 skipped (the real-login step, machine release, the 1 vs 2-GPU step, and the failure test that needs the short settings) |
| Browser tests, real stack (`npm run test:e2e`) | **6 of 6 passed**, 8.6 s: projects; datasets (real CSV uploads, versions, retry, isolation); upload lock; job form and detail (version, retry, cancel, isolation); a **live CPU job submitted in the browser**, followed to its MLflow results; compare and usage pages (gateway only) |

**What it means.** With every portal page on `main`, a user can go through the website from project to dataset
to training job to results, with the browser talking only to the portal and the gateway. Not covered here: the
real sign-in (dev token), the 1 vs 2-GPU comparison (no runs yet, #28), and the cloud (no AWS account).
