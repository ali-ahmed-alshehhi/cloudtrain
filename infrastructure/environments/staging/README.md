# Environment: staging

Owners: Hamda + Fatma. Uses the modules in `../../modules/` with staging-sized values
(e.g. worker capacity). Its state is stored in the S3 backend under `cloudtrain/staging/terraform.tfstate`.
Used for the approval step before promoting a change (Salem's pipeline).
