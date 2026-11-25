# 0009 — Terraform local practice uses LocalStack (not AWS Emulator)

- **Status:** superseded by [0011](0011-aws-emulator-instead-of-aws-account.md)
- **Date:** 2026-11-15
- **Decided by:** Hamda + Fatma (Student 6), following Ali’s review on PR #92

## Context
Student 6 briefly pointed Terraform at the official [AWS Emulator](https://github.com/aws/aws-emulator)
as a second local “AWS account.” The app already uses **LocalStack** for S3 and SQS on laptops
([0005](0005-localstack-for-s3.md)). Running two local AWS stand-ins confuses the team about which
tool to use.

## Decision
1. **Terraform practice on laptops uses LocalStack** — the same product as `docker-compose.yml`
   (image `localstack/localstack:4.14`). Student 6 may start a small compose file under
   `infrastructure/` that publishes the edge port so `terraform apply` can run from the host.
2. **We do not adopt AWS Emulator** for CloudTrain. No second emulator in the shared workflow.
3. **Real AWS** remains required for graded cloud demos and for services LocalStack Community does
   not cover well enough for us (RDS, ECS Fargate, GPU EC2, Cognito, etc.).

## Why
One local AWS API for everyone (aligns with 0005). Less to install, document and debug. Emulator
would only help for some extra APIs, and those still need real AWS for the final demo.

## Trade-offs
LocalStack Community is incomplete for RDS/ECS/GPU. That is acceptable: those modules are applied
against the instructors’ real AWS account, not against a laptop emulator.

## Upgrade path
If instructors later mandate AWS Emulator, revisit this ADR with a pinned package + checksum and a
team migration note. Until then, LocalStack only.
