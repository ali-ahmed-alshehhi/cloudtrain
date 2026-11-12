# CloudTrain — final technical report (outline)

**Editor:** Ali. Each owner writes their own section. Due **Fri 27 Nov 2026**.

## 1. The key question
*How do we turn an ML training script into a scalable, automated, reliable and reusable cloud ML service?*
- Why a pile of separate Python scripts is not enough for a production ML platform
- How microservices, cloud infrastructure, distributed computing and DevOps solve that

## 2. Architecture
Diagrams and service boundaries (from `docs/ARCHITECTURE.md`); how the 8 logical services are covered.

## 3. Each subsystem (one section per student)
For each: what it does, design, API, data, tests, how it integrates, what works.
1. Gateway, Projects and integration — Ali
2. Datasets and storage — Faisal
3. Training job management — Mariam
4. Training engine and MLflow — Abdullah
5. Distributed training and parallelism — Ahmed + Abdulla
6. Terraform and cloud infrastructure — Hamda + Fatma
7. Scheduling and compute — Maitha
8. Model registry, deployment and inference — Majed
9. CI/CD and security — Salem
10. Portal, observability and evaluation — Hilal + Adel

## 4. Engineering decisions and trade-offs
Summary of `docs/decisions/`, each with its measured effect where we have one.

## 5. Results
Benchmarks (`docs/BENCHMARKS.md`), evaluation (`docs/EVALUATION.md`), test results (`docs/TESTING.md`).

## 6. Limitations

## 7. Lessons learned

## 8. Learning outcomes covered
How the project shows each of the 10 outcomes: architecture and decomposition; REST and service
communication; databases, storage and messaging; Docker; Terraform; cloud provisioning, networking,
security and storage; distributed training; CI/CD; model versioning, tracking and serving;
observability, failure recovery, scalability and cost.
