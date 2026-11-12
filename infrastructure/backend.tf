# Remote state: stored in S3, with locking, never in Git.
# Owners: Hamda + Fatma.
#
# The bucket name and region are passed at init time, so no account details are committed:
#   terraform init -backend-config="bucket=<state bucket>" -backend-config="region=<region>" \
#                  -backend-config="key=cloudtrain/<environment>/terraform.tfstate"
# The state bucket itself is created once (bootstrap) and documented in docs/DEPLOYMENT_GUIDE.md.

terraform {
  backend "s3" {
    encrypt      = true
    use_lockfile = true # S3-native state locking
  }
}
