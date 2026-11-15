# Environment: dev

Owners: Hamda + Fatma.

| File | Purpose |
|---|---|
| `emulator.tfvars.example` | Official AWS Emulator practice (Student 6 fake account) |
| `terraform.tfvars.example` | Real AWS values (copy to git-ignored `terraform.tfvars`) |

```bash
./scripts/emulator-up.sh
source ./scripts/emulator-env.sh
terraform apply -var-file=environments/dev/emulator.tfvars.example
```
