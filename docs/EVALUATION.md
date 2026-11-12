# Evaluation: performance, reliability and cloud cost

**Owners:** Hilal + Adel (Student 10). Template: fill in with measurements from the integrated system.

## 1. Performance
- Gateway latency (p50 / p95) per route
- Time from `POST /jobs` to RUNNING (queue + scheduling time)
- Inference latency for `POST /predict`
- Dataset upload and download speed

## 2. Reliability
- Failure-recovery test: worker killed mid-job → time to detect (heartbeat timeout) → retry → finished
- What happens when each service is stopped (gateway answers 503, nothing hangs)
- Restarting containers keeps datasets, models, experiments and job records

## 3. Scalability
- What scales separately (inference vs training) and how
- Single-GPU vs DDP summary (details in `docs/BENCHMARKS.md`)

## 4. Cloud cost
- Cost per job and per project (from the portal)
- Total cloud spend for the project, by resource type
- What we did to keep cost down (GPU machines only while jobs run, `terraform destroy`)

## 5. Limitations
