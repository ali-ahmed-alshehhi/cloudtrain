import test from "node:test";
import assert from "node:assert/strict";
import { localDevToken } from "../app/lib/dev-session.mjs";

test("local dev token supports old Compose env files without ENVIRONMENT", () => {
  assert.equal(localDevToken({ AUTH_MODE: "dev", DEV_AUTH_TOKEN: "fixture" }), "fixture");
  assert.equal(localDevToken({ AUTH_MODE: "dev", ENVIRONMENT: "local", DEV_AUTH_TOKEN: "fixture" }), "fixture");
});
test("real login and nonlocal environments never expose the dev token", () => {
  for (const ENVIRONMENT of ["production", "staging", "dev"]) {
    assert.equal(localDevToken({ AUTH_MODE: "dev", ENVIRONMENT, DEV_AUTH_TOKEN: "fixture" }), "");
  }
  assert.equal(localDevToken({ AUTH_MODE: "jwt", DEV_AUTH_TOKEN: "fixture" }), "");
  assert.equal(localDevToken({ DEV_AUTH_TOKEN: "fixture" }), "");
});
