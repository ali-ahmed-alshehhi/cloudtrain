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

## Wiring it into the root module (Hamda + Fatma)
```hcl
module "identity" {
  source = "./modules/identity"

  environment                = var.environment
  aws_region                 = var.aws_region
  issuer_base_url            = var.use_emulator ? var.emulator_endpoint : ""
  allow_admin_password_login = var.use_emulator
}
```
and add `cognitoidp = local.practice_endpoint` to the provider's `endpoints` block.
