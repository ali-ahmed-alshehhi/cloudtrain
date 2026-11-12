# Deployment guide

**Owners:** Hamda + Fatma (Student 6), with Salem (pipeline) and Ali (integration).
How to provision, operate and destroy the CloudTrain cloud environment. Template: fill in as you build.

## 1. Before you start
- AWS account, region and budget: _(see docs/OPEN_DECISIONS.md #1)_
- Tools: Terraform version, AWS CLI, how to log in to AWS (no long-lived keys on laptops)
- GPU quota status

## 2. One-time bootstrap: the state bucket
_How the S3 state bucket is created, who can access it, and how locking works._

## 3. Create an environment (`dev`, `staging`)
```bash
# commands here
```
What `terraform plan` should show; how long `apply` takes.

## 4. Deploy the services
_How images get to ECR and services to ECS Fargate (Salem's pipeline)._

## 5. Change something through Terraform
_Example: change worker capacity, plan, apply — no manual changes._

## 6. Operate
- Where the logs and dashboards are
- How to see what a job costs
- What to do when a worker machine is stuck

## 7. Destroy
```bash
# terraform destroy for disposable environments
```
_What is kept (state bucket?) and what is removed. Run after every test session and after submission._

## 8. Cost notes
_Which resources cost money while idle, and how we keep GPU machines off when no job runs._
