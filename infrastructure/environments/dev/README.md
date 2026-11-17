# Environment: dev

Owners: Hamda + Fatma.

| File | Purpose |
|---|---|
| `emulator.tfvars.example` | AWS Emulator, our stand-in for an AWS account (decision 0011) |
| `localstack.tfvars.example` | LocalStack (same tool as the app — decision 0005) |
| `terraform.tfvars.example` | Real AWS values (copy to git-ignored `terraform.tfvars`) |

```bash
./scripts/emulator-up.sh
source ./scripts/emulator-env.sh
terraform apply -var-file=environments/dev/emulator.tfvars.example
```
