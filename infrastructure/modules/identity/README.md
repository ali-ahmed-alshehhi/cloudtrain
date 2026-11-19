# identity — login with Amazon Cognito

Written by Salem (Student 9) for decision [0006](../../../docs/decisions/0006-login-provider-cognito.md);
owners of the folder: Hamda + Fatma.

Creates one **user pool** (no self sign-up, strong passwords), one **app client** for the portal
(no secret, one-hour tokens), and three **role groups**: `admin`, `data-scientist`, `viewer`.

Its outputs are the gateway's three settings: `issuer` → `JWT_ISSUER`, `portal_client_id` →
`JWT_AUDIENCE`, `jwks_url` → `JWT_JWKS_URL`.

## Used today
`security/login/terraform` applies this module on the AWS Emulator, and `security/login/setup.sh`
adds test users. See [`security/login/README.md`](../../../security/login/README.md).

## Wired into the root module (Hamda + Fatma)
Root `main.tf` enables this with `enable_identity = true` (see `environments/dev/emulator.tfvars.example`).
The AWS provider endpoints block includes `cognitoidp = local.practice_endpoint` for the emulator.

Outputs after apply: `jwt_issuer`, `jwt_audience`, `jwt_jwks_url` (gateway `JWT_*` settings).

Salem’s `security/login/` stack can still apply this module on its own for login CI; the root
wiring is for the shared CloudTrain Terraform apply.
