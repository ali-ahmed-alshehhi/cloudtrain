# 0011 — The AWS Emulator stands in for an AWS account

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** Hamda + Fatma (Student 6) with Ali, after the instructors' guidance
- **Supersedes:** [0009](0009-terraform-local-uses-localstack.md)

## Context
We planned to apply Terraform against an AWS account from the instructors (OPEN_DECISIONS #1).
The instructors asked us instead to run a simulator on our laptops and use it for the tasks we
wanted AWS to do. Decision 0009 had picked LocalStack for Terraform practice and said real AWS was
still needed for the graded demos, and that we would revisit it if the AWS Emulator was required.

## Decision
1. Terraform targets the official [AWS Emulator](https://github.com/aws/aws-emulator) instead of an
   AWS account: `use_emulator = true` (see `infrastructure/environments/dev/emulator.tfvars.example`).
   Start it with `infrastructure/scripts/emulator-up.sh`, then `source infrastructure/scripts/emulator-env.sh`.
2. Remote state lives in an S3 bucket on the emulator, created by `infrastructure/bootstrap/`,
   with S3-native locking (`use_lockfile`). See `infrastructure/backends/emulator.s3.backend.hcl.example`.
3. The app's `make up` keeps LocalStack for S3 and SQS on laptops (decision 0005). Nothing changes
   for the services.
4. `use_localstack` stays in the Terraform code, so LocalStack still works for anyone who needs it.

## Why
- No AWS account, no bill, and no wait for GPU quota.
- The emulator implements the services our modules use (S3, SQS, ECR, EC2/VPC, RDS, Secrets
  Manager, ECS, IAM, CloudWatch), so the seven Terraform demos can run on a laptop.
- It is the instructors' guidance.

## Trade-offs
- The emulator does not run real machines: no real GPU training, no real containers on ECS. Results
  that need real hardware (for example 1 GPU vs 2 GPU benchmarks) must say they were not measured
  on AWS.
- Some behaviours differ from AWS. Known gaps are listed in the emulator repository under
  `issues/things-that-do-not-work/`. Check there before blaming our code.
- The emulator's RDS has no schemas (found by Mariam on #66, 19 Nov 2026): `CREATE SCHEMA` and
  schema-qualified tables answer a syntax error, so `infrastructure/scripts/bootstrap-schemas.sh`
  only works on real AWS. Services keep the real PostgreSQL from `make up` for their tables.
- Everyone who runs Terraform needs Docker and about 2 GB of free memory for the emulator container.

## Upgrade path
If an AWS account becomes available, set `use_emulator = false`, run `infrastructure/bootstrap/` once
in that account, and use `backends/dev.s3.backend.hcl.example`. The modules do not change.
