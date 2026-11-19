# Remote-state bootstrap — `infrastructure/bootstrap/`

**Owners:** Hamda + Fatma (Student 6)

Terraform remembers what it built in a **state file**. On one laptop that file can sit next to the
code, but a team needs one shared copy that two people can't change at the same time. This folder
creates the S3 bucket that holds that shared copy. Run it **once per account**: once on the AWS
Emulator (decision [0011](../../docs/decisions/0011-aws-emulator-instead-of-aws-account.md)), and
once more only if we ever get a real AWS account.

The bucket is:
- **versioned**, so every earlier state can be recovered after a bad apply;
- **encrypted** (AES256) and **never public** (public access block);
- **TLS only**: a bucket policy refuses any request that isn't HTTPS;
- **tidy**: old state versions are removed after 90 days.

**Locking:** the root module's backend uses `use_lockfile = true`. While a `plan` or `apply` runs,
Terraform writes `<key>.tflock` next to the state. A second person who starts at the same time gets
"Error acquiring the state lock" instead of corrupting the state. No DynamoDB table is needed.

This folder keeps its own small local state file (`terraform.tfstate`, ignored by git), because the
bucket can't hold the state of the thing that creates it.

## Needs
- Terraform **1.10 or later** (`terraform version`), for `use_lockfile`.
- Docker, for the emulator.

## Run it on the AWS Emulator

```bash
cd infrastructure
./scripts/emulator-up.sh
source ./scripts/emulator-env.sh        # every new terminal needs this again

# 1. Create the state bucket (once)
cd bootstrap
terraform init
terraform apply -var-file=emulator.tfvars.example
cd ..
```

## Move the root module's state into the bucket

```bash
# still in infrastructure/, with emulator-env.sh sourced
terraform init
terraform apply -var-file=environments/dev/emulator.tfvars.example   # state is still local here

cp backends/s3.backend.tf.example backend.tf                         # do NOT commit this change
terraform init -migrate-state -backend-config=backends/emulator.s3.backend.hcl.example
# answer "yes" to copy the existing state to the new backend

terraform state list        # now read from s3://cloudtrain-tfstate/cloudtrain/dev/terraform.tfstate
```

**See the lock work:** open a second terminal (`source scripts/emulator-env.sh` there too) and run
`terraform plan -var-file=environments/dev/emulator.tfvars.example` in both at the same moment.
One of them stops with "Error acquiring the state lock".

## Clean up

```bash
# in infrastructure/
terraform destroy -var-file=environments/dev/emulator.tfvars.example

git restore backend.tf                   # back to the team's default (local state)
terraform init -migrate-state            # copies the (now empty) state back to a local file

cd bootstrap
terraform destroy -var-file=emulator.tfvars.example
cd ..
./scripts/emulator-down.sh
```

On real AWS, `terraform destroy` here refuses while state files are still in the bucket
(`force_destroy` is only on for the emulator), so the team's state can't be deleted by accident.

## If something goes wrong
- **`x509: certificate signed by unknown authority`**: you didn't `source scripts/emulator-env.sh` in
  this terminal. It sets `AWS_CA_BUNDLE` to the emulator's certificate.
- **`NoCredentialProviders` / `no valid credential sources`**: same fix, it also sets the emulator's
  credentials file.
- **`Unsupported argument "use_lockfile"`**: your Terraform is older than 1.10. Update it.
- **`AccessDenied` on the state bucket**: set `enforce_tls = false` in your tfvars, apply again, and
  tell Hamda/Fatma, so we can report it to the emulator's issue list.
