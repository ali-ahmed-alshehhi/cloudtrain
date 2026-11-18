## Summary

Student 6 (Hamda + Fatma) Terraform starter: S3, SQS, VPC/security, ECR modules wired for
`dev`, with LocalStack practice (same tool as the app) and docs for real AWS later.

Refs [S6 Hamda + Fatma] Fri 13 – Sun 15 Nov: Remote state in S3 with locking #33  
Refs [S6 Hamda + Fatma] Mon 16 – Wed 18 Nov: Dev environment: S3 buckets, database, queues, image registry #34

## What changed

- Modules: `networking`, `security`, `object-storage`, `message-queue`, `container-registry`
- Root wiring: `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, local `backend.tf`
- Local practice: LocalStack (`docker-compose.localstack.yml` + `localstack.tfvars.example`) — decisions 0005 / **0007**
- Real AWS path: `terraform.tfvars.example` + S3 backend examples
- Docs: `infrastructure/README.md`, `docs/DEPLOYMENT_GUIDE.md`
- Checkov findings addressed so CI can pass
- Removed the temporary AWS Emulator path (second local AWS stand-in) per review

## Checklist

- [x] Buckets encrypted, versioned, private (block public access)
- [x] SQS `training-jobs` + DLQ + `job-events` with names teammates already use
- [x] Every resource tagged `Project` / `Environment` / `Owner` (provider `default_tags`)
- [x] Local practice uses **LocalStack** (not a second emulator) — ADR 0007
- [x] Networking / ECR gated off on LocalStack; on for real AWS tfvars
- [x] Remote-state S3 backend examples ready (apply on real AWS when account exists)
- [x] `terraform fmt` / validate + Checkov clean for this PR
- [ ] Fatma re-approve after this push
- [ ] Ali approve / merge

## How to try locally

```bash
cd infrastructure
docker compose -f docker-compose.localstack.yml up -d
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
terraform init
terraform apply -var-file=environments/dev/localstack.tfvars.example
terraform destroy -var-file=environments/dev/localstack.tfvars.example
docker compose -f docker-compose.localstack.yml down
```
