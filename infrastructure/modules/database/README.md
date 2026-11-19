# Module: database

Owners: Hamda + Fatma.

RDS PostgreSQL, encrypted, private, with one database and **one schema + user per service**
(`projects`, `datasets`, `jobs`, `scheduler`, `registry`, `mlflow`) — same as local `postgres` init.

## What Terraform creates
- RDS Postgres instance in private subnets
- DB subnet group + uses the database security group from `modules/security`
- Master password managed by RDS in **Secrets Manager** (`manage_master_user_password = true`;
  password never stored in Terraform state). ARN via `terraform output db_master_secret_arn`.

## After first apply (one-time)
```bash
# From a host that can reach the private RDS (bastion / VPN / SSM):
cd infrastructure
export MASTER_SECRET_ARN="$(terraform output -raw db_master_secret_arn)"
ENVIRONMENT=dev ./scripts/bootstrap-schemas.sh
```
The script reads **username/password** from the RDS-managed secret, and **host/port/dbname**
from terraform outputs (`db_address`, `db_port`, `db_name`). It creates the six service
roles/schemas (mirrors `local/postgres/init.sh`) and writes each service `DATABASE_URL`
(with `?sslmode=require`) to Secrets Manager as `cloudtrain/<env>/database/<service>` —
passwords are not printed.

## LocalStack note
Keep `enable_database = false` for LocalStack practice. Use real AWS for this module.
