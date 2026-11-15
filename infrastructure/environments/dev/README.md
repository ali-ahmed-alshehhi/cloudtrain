# Environment: dev

Owners: Hamda + Fatma.

| File | Purpose |
|---|---|
| `localstack.tfvars.example` | LocalStack practice (same tool as the app — decisions 0005 / 0007) |
| `terraform.tfvars.example` | Real AWS values (copy to git-ignored `terraform.tfvars`) |

```bash
docker compose -f docker-compose.localstack.yml up -d
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
terraform apply -var-file=environments/dev/localstack.tfvars.example
```
