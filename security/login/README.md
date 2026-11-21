# Real login on the AWS Emulator

Owner: Salem (Student 9). Decision [0006](../../docs/decisions/0006-login-provider-cognito.md)
(Cognito), on the AWS Emulator of decision [0011](../../docs/decisions/0011-aws-emulator-instead-of-aws-account.md).

`make up` keeps the **dev token** (`AUTH_MODE=dev`): nobody needs the emulator to work on a service.
This folder turns on the **real login** when you want it: real Cognito users, real signed tokens,
checked by the gateway with `AUTH_MODE=jwt`.

## Try it (about 3 minutes)
Needs Docker, Terraform and the AWS CLI.

```bash
infrastructure/scripts/emulator-up.sh        # 1. the AWS Emulator
security/login/setup.sh                      # 2. user pool, app client, roles, test users
docker compose -f docker-compose.yml -f security/login/compose.login.yml up -d --build --wait

TOKEN=$(security/login/token.sh alice)       # 3. log in as Alice
curl -H "Authorization: Bearer $TOKEN" http://localhost:5810/api/v1/projects     # 200
DEV=$(grep ^DEV_AUTH_TOKEN= .env | cut -d= -f2)   # the laptop dev token
curl -H "Authorization: Bearer $DEV" http://localhost:5810/api/v1/projects     # 401
```

Back to the dev token: `make up` again.

## What gets created
| Thing | Details |
|---|---|
| User pool `dev-cloudtrain-users` | no self sign-up; passwords of 12+ characters with upper, lower, number and symbol |
| App client `dev-cloudtrain-portal` | no secret (the portal runs in a browser); tokens valid one hour |
| Role groups | `admin`, `data-scientist`, `viewer`; they arrive in the token as `cognito:groups` |
| Test users | `alice`, `bob` (data-scientist), `vera` (viewer), with **random** passwords in `.local/users.env` |
| Gateway settings | `.local/gateway.env`: `AUTH_MODE=jwt`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_JWKS_URL` |

Everything in `.local/` is git-ignored. Run `setup.sh` again at any time (new passwords).

## The one emulator-only part
The emulator's TLS certificate only covers `127.0.0.1`, so the gateway container cannot fetch the
public keys from it. `compose.login.yml` adds a tiny `login-keys` web server that serves a copy of
the **public** keys inside Docker only. On AWS, `JWT_JWKS_URL` is Cognito's own https address
(output `jwks_url` of `infrastructure/modules/identity`) and `login-keys` is not used.

## Tests
`security/tests/test_login.py`, run by `.github/workflows/login.yml` on every pull request that
touches the login, the gateway or the projects service:

| Test | Expected |
|---|---|
| A real Cognito ID token | 200 |
| The token's issuer, audience and role group are right | ✅ |
| No token / the laptop dev token | 401 |
| A token whose content was changed (another user, `admin` role) | 401 |
| A token signed with another key, or not signed at all | 401 |
| A token made for another app, or an access token | 401 |
| Bob and Vera open or list Alice's project | 403 / not listed |

For the portal (Hilal + Adel): log in with the app client ID from `.local/login.env` and send the
**ID token** as `Authorization: Bearer <token>`.
