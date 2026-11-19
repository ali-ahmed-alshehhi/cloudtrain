# The gateway's three login settings (decision 0006). None of these is a secret.

output "user_pool_id" {
  value = aws_cognito_user_pool.users.id
}

output "portal_client_id" {
  description = "JWT_AUDIENCE for the gateway, and the client ID for the portal's login page."
  value       = aws_cognito_user_pool_client.portal.id
}

output "issuer" {
  description = "JWT_ISSUER for the gateway."
  value       = local.issuer
}

output "jwks_url" {
  description = "JWT_JWKS_URL for the gateway: the user pool's public keys."
  value       = "${local.issuer}/.well-known/jwks.json"
}

output "role_groups" {
  value = keys(aws_cognito_user_group.roles)
}
