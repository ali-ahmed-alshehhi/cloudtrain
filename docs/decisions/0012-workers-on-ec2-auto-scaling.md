# 0012 — Training workers run on EC2 in an Auto Scaling group

- **Status:** accepted (Hamda on #123, Maitha on #70, 19 Nov 2026)
- **Date:** 2026-11-18
- **Decided by:** Fatma and Hamda (Student 6), with Maitha (Scheduler)

## Context
The training workers need machines with GPUs. The choice was plain EC2 machines in an Auto Scaling
group, or AWS Batch. There is no AWS account: Terraform runs against the AWS Emulator (0011).

## Decision
Workers are EC2 machines in an Auto Scaling group (`infrastructure/modules/training-compute`). The
number of machines is the variable `worker_desired_capacity`.

## Why
- Demo 4 is "change worker capacity, apply, no manual rebuild". With an Auto Scaling group that is
  one number in a tfvars file and one `terraform apply`.
- Maitha's Scheduler already decides which job goes to which worker, so Batch's own job queue
  would do the same job twice.
- The emulator has an Auto Scaling service. We could not confirm anything for Batch.
- It is the simpler design to explain, and it is also right on real AWS (see 0011, upgrade path).

## Trade-offs
- We start and stop machines ourselves (by capacity) instead of Batch doing it per job.
- On the emulator no real GPU runs. Training speed must not be reported as measured on AWS.
