# Login (decision 0006): one Cognito user pool, one app client for the portal, three role groups.
# Written by Salem (Student 9), reviewed by Hamda + Fatma. Used by security/login/terraform today,
# and by the root module once it is wired in (see README.md).

resource "aws_cognito_user_pool" "users" {
  name = "${var.environment}-cloudtrain-users"

  # Nobody can sign themselves up: accounts are created by an admin (or the setup script).
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 3
  }

  username_configuration {
    case_sensitive = false
  }

  deletion_protection = var.deletion_protection ? "ACTIVE" : "INACTIVE"

  tags = {
    Name    = "${var.environment}-cloudtrain-users"
    Purpose = "login"
  }
}

# The portal is a browser app: it cannot keep a secret, so the client has none.
resource "aws_cognito_user_pool_client" "portal" {
  name         = "${var.environment}-cloudtrain-portal"
  user_pool_id = aws_cognito_user_pool.users.id

  generate_secret = false
  explicit_auth_flows = compact([
    "ALLOW_USER_SRP_AUTH", # the portal: the password never leaves the browser in clear
    "ALLOW_REFRESH_TOKEN_AUTH",
    var.allow_admin_password_login ? "ALLOW_ADMIN_USER_PASSWORD_AUTH" : "", # test script, emulator only
  ])

  prevent_user_existence_errors = "ENABLED" # a wrong user name and a wrong password look the same
  enable_token_revocation       = true

  # A stolen token is useful for one hour at most.
  id_token_validity      = 60
  access_token_validity  = 60
  refresh_token_validity = 1
  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }
}

# Roles. They arrive in the ID token as "cognito:groups".
resource "aws_cognito_user_group" "roles" {
  for_each = var.roles

  name         = each.key
  description  = each.value
  user_pool_id = aws_cognito_user_pool.users.id
}

locals {
  # On AWS the issuer is the regional Cognito address. On the AWS Emulator it is the emulator's
  # address (decision 0011). The gateway compares this string with the token's "iss" claim.
  issuer = (
    var.issuer_base_url != ""
    ? "${trimsuffix(var.issuer_base_url, "/")}/${aws_cognito_user_pool.users.id}"
    : "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
  )
}
