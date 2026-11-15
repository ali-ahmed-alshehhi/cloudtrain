# Environment: dev

Owners: Hamda + Fatma. Uses the modules in `../../modules/` with dev-sized values.
State on real AWS: S3 key `cloudtrain/dev/terraform.tfstate`.

| File | Purpose |
|---|---|
| `terraform.tfvars.example` | Real AWS values (copy to git-ignored `terraform.tfvars`) |
| `localstack.tfvars.example` | Local practice against `docker-compose.localstack.yml` |

Disposable: `terraform destroy` after each test session.
