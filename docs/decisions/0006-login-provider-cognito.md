# 0006 — Amazon Cognito as the login provider

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Salem (Open decision #3)

## Context
The gateway has one login function, `verify_token()` in `gateway/app/auth.py`. On laptops it uses
`AUTH_MODE=dev` (one fixed fake token). In the cloud it uses `AUTH_MODE=jwt`: it checks a signed
login token (RS256) against the provider's public keys (`JWT_JWKS_URL`) and reads the user from
`sub`. We need a provider that issues those tokens. Options: Amazon Cognito, Keycloak (self-hosted),
an external service such as Auth0.

## Decision
Use an **Amazon Cognito user pool**, created by Terraform (with Hamda + Fatma), with one app client
for the portal. The gateway checks Cognito **ID tokens**:

| Gateway setting | Value |
|---|---|
| `AUTH_MODE` | `jwt` |
| `JWT_ISSUER` | `https://cognito-idp.<region>.amazonaws.com/<user pool ID>` |
| `JWT_JWKS_URL` | the issuer + `/.well-known/jwks.json` |
| `JWT_AUDIENCE` | the portal's app client ID |

These are not secrets (they are public by design); they still come from Terraform outputs, not
from the code. Laptops and CI keep `AUTH_MODE=dev`, so nobody needs AWS to run the project.

Roles later: Cognito **groups** `admin`, `data-scientist`, `viewer` arrive in the token as
`cognito:groups`.

## Why
- We are on AWS already: no extra server to run, patch or keep alive (Keycloak would be one more
  container with its own database).
- It is managed by Terraform like the rest of the platform, and its cost at class size is covered
  by the free tier.
- It is standard OpenID Connect, so the gateway code does not depend on Cognito: switching provider
  later means changing the three settings above.

## Trade-offs
- Using the **ID token** (not the access token) is what lets the gateway check the audience with the
  existing code, because Cognito access tokens carry `client_id` instead of `aud`. Fine for a portal
  that is our only client; a machine-to-machine client would need the access token and a
  `client_id` check.
- Cognito's hosted login page looks plain; the portal can use it as is.
- Users exist only in the cloud. Local development keeps the fake login.
