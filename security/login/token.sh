#!/usr/bin/env bash
# Log in as a test user on the AWS Emulator and print the ID token (owner: Salem).
#
#   security/login/token.sh alice                 # ID token for the portal app (what the gateway accepts)
#   security/login/token.sh alice --access        # access token instead (the gateway refuses it)
#   security/login/token.sh alice --other-app     # ID token made for another app (the gateway refuses it)
#
#   TOKEN=$(security/login/token.sh alice)
#   curl -H "Authorization: Bearer $TOKEN" http://localhost:5810/api/v1/projects
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
USER_NAME=${1:?usage: token.sh <alice|bob|vera> [--access|--other-app]}
KIND=${2:-}

[[ -f "$HERE/.local/login.env" ]] || { echo "Run security/login/setup.sh first." >&2; exit 1; }
# shellcheck source=/dev/null
source "$ROOT/infrastructure/scripts/emulator-env.sh" >/dev/null
# shellcheck source=/dev/null
source "$HERE/.local/login.env"
# shellcheck source=/dev/null
source "$HERE/.local/users.env"
password_var="PASSWORD_${USER_NAME}"
PASSWORD=${!password_var:?unknown test user: $USER_NAME}

client=$CLIENT_ID
field=IdToken
[[ "$KIND" == "--access" ]] && field=AccessToken
[[ "$KIND" == "--other-app" ]] && client=$OTHER_CLIENT_ID

aws cognito-idp admin-initiate-auth --user-pool-id "$POOL_ID" --client-id "$client" \
  --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters "USERNAME=$USER_NAME,PASSWORD=$PASSWORD" \
  --query "AuthenticationResult.$field" --output text
