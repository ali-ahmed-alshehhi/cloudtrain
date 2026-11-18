# Module: database

Owners: Hamda + Fatma.

RDS PostgreSQL, encrypted, private, with one database and **one schema + user per service**
(`projects`, `datasets`, `jobs`, `scheduler`, `registry`, `mlflow`) — same as local `postgres` init.

## What Terraform creates
- RDS Postgres instance in private subnets
- DB subnet group + uses the database security group from `modules/security`
- Master password in **Secrets Manager** (`cloudtrain/<env>/database/master`)

## After first apply (one-time)
```bash
# From a host that can reach the private RDS (bastion / VPN / SSM):
./scripts/bootstrap-schemas.sh
```
That creates the six service roles/schemas (mirrors `local/postgres/init.sh`).

## Emulator note
Keep `enable_database = false` for AWS Emulator practice. Use real AWS (or LocalStack Pro /
Emulator RDS fidelity) for this module.
