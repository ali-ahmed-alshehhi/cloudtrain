# Environment: dev

Owners: Hamda + Fatma. Uses the modules in `../../modules/` with dev-sized values
(e.g. worker capacity). Its state is stored in the S3 backend under `cloudtrain/dev/terraform.tfstate`.
Disposable: `terraform destroy` after each test session.
