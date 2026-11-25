// Compose defaults to local when ENVIRONMENT is omitted in an older .env file.
export function localDevToken(env) {
  return env.AUTH_MODE === "dev" && (!env.ENVIRONMENT || env.ENVIRONMENT === "local")
    ? env.DEV_AUTH_TOKEN || "" : "";
}
