#!/usr/bin/env bash
# Real login on the AWS Emulator, in one command (owner: Salem, task #53).
#
#   1. creates the Cognito user pool, portal app client and role groups (Terraform)
#   2. adds three test users with random passwords: alice and bob (data-scientist), vera (viewer)
#   3. writes the gateway's login settings to security/login/.local/gateway.env
#
# Needs the AWS Emulator running (infrastructure/scripts/emulator-up.sh), Terraform and the AWS CLI.
# Then start everything with the real login:
#   docker compose -f docker-compose.yml -f security/login/compose.login.yml up -d --build --wait
# and get a token with:  security/login/token.sh alice
#
# Everything it writes stays in security/login/.local/ (git-ignored). Run it again at any time.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LOCAL="$HERE/.local"

# shellcheck source=/dev/null
source "$ROOT/infrastructure/scripts/emulator-env.sh" >/dev/null

mkdir -p "$LOCAL"
chmod 700 "$LOCAL"

echo "1/3 Cognito user pool, app client and role groups (Terraform)"
terraform -chdir="$HERE/terraform" init -input=false >/dev/null
terraform -chdir="$HERE/terraform" apply -input=false -auto-approve >/dev/null
out() { terraform -chdir="$HERE/terraform" output -raw "$1"; }
POOL_ID=$(out user_pool_id)
CLIENT_ID=$(out portal_client_id)
ISSUER=$(out issuer)
JWKS_URL=$(out jwks_url)

# A second app client, only for the test "a token made for another app is refused".
OTHER_CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" \
  --query "UserPoolClients[?ClientName=='test-other-app'].ClientId | [0]" --output text)
if [[ -z "$OTHER_CLIENT_ID" || "$OTHER_CLIENT_ID" == "None" ]]; then
  OTHER_CLIENT_ID=$(aws cognito-idp create-user-pool-client --user-pool-id "$POOL_ID" \
    --client-name test-other-app --explicit-auth-flows ALLOW_ADMIN_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH \
    --query UserPoolClient.ClientId --output text)
fi

echo "2/3 Test users"
: >"$LOCAL/users.env"
chmod 600 "$LOCAL/users.env"
add_user() { # name group
  local name=$1 group=$2 password
  # Random each run; meets the pool's policy (upper, lower, number, symbol, 12+ characters)
  password="Ct9!$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
  aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username "$name" \
    --message-action SUPPRESS >/dev/null 2>&1 || true # already exists on a re-run
  aws cognito-idp admin-set-user-password --user-pool-id "$POOL_ID" --username "$name" \
    --password "$password" --permanent
  aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL_ID" --username "$name" --group-name "$group"
  echo "PASSWORD_${name}=${password}" >>"$LOCAL/users.env"
  echo "   $name ($group)"
}
add_user alice data-scientist
add_user bob data-scientist
add_user vera viewer

echo "3/3 Gateway settings"
# The emulator's TLS certificate only covers 127.0.0.1, so the gateway container cannot download
# the keys from it. We give the gateway a copy of the PUBLIC keys instead (not a secret).
# On AWS, JWT_JWKS_URL is the https address from the module output and this copy is not needed.
curl -fsS --cacert "$AWS_CA_BUNDLE" "$JWKS_URL" -o "$LOCAL/jwks.json"
cat >"$LOCAL/gateway.env" <<EOF
AUTH_MODE=jwt
JWT_ISSUER=$ISSUER
JWT_AUDIENCE=$CLIENT_ID
JWT_JWKS_URL=file:///login/jwks.json
EOF
cat >"$LOCAL/login.env" <<EOF
POOL_ID=$POOL_ID
CLIENT_ID=$CLIENT_ID
OTHER_CLIENT_ID=$OTHER_CLIENT_ID
ISSUER=$ISSUER
JWKS_URL=$JWKS_URL
EOF

echo
echo "Done. Gateway settings in security/login/.local/gateway.env:"
sed 's/^/   /' "$LOCAL/gateway.env"
echo "Start:  docker compose -f docker-compose.yml -f security/login/compose.login.yml up -d --build --wait"
echo "Token:  security/login/token.sh alice"
