# Point AWS CLI / SDKs / Terraform at the local AWS Emulator.
# Usage:  source ./scripts/emulator-env.sh
#
# Docs: https://docs.aws.amazon.com/emulator/latest/userguide/point-sdk-to-emulator.html

EMU_PORT="${EMU_PORT:-9297}"
EMU_DIR="${HOME}/.aws/emulator/${EMU_PORT}"

if [[ ! -f "${EMU_DIR}/emulator_credentials" ]]; then
  echo "Emulator credentials not found at ${EMU_DIR}/emulator_credentials"
  echo "Run ./scripts/emulator-up.sh first."
  return 1 2>/dev/null || exit 1
fi

# Do not use real AWS keys with the emulator
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_SECURITY_TOKEN

export AWS_ENDPOINT_URL="https://127.0.0.1:${EMU_PORT}"
export AWS_SHARED_CREDENTIALS_FILE="${EMU_DIR}/emulator_credentials"
export AWS_CONFIG_FILE="${EMU_DIR}/config"
export AWS_CA_BUNDLE="${EMU_DIR}/ca.pem"
export AWS_EC2_METADATA_DISABLED=true
export AWS_DISABLE_HOST_PREFIX_INJECTION=true
export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# Terraform S3 control API sometimes rewrites the host; pin it to the emulator
export AWS_ENDPOINT_URL_S3_CONTROL="https://127.0.0.1:${EMU_PORT}"

echo "AWS tools now point at ${AWS_ENDPOINT_URL}"
echo "Credentials: ${AWS_SHARED_CREDENTIALS_FILE}"
