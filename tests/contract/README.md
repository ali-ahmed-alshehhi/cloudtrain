# Contract tests — `tests/contract/`

**Owner:** Ali. Run with `make contract` after `make up`.

[Schemathesis](https://schemathesis.readthedocs.io/) reads each service's file in `contracts/openapi/`,
sends many generated requests (valid and invalid) to the running service, and fails if an answer
breaks the contract: an undocumented status code, a body of the wrong shape, a wrong content type,
or any 500 error.

It runs inside a small container on the docker-compose network (`docker-compose.yml`, profile
`tools`), so it reaches every service directly, internal endpoints included, without publishing any
extra ports. Set `CONTRACT_MAX_EXAMPLES` to send more requests per endpoint (default 30).

Note: the generated requests create real records (random projects, datasets, ...) in the running
system. Use `make reset` to start clean.
