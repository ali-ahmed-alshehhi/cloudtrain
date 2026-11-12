# 0001 — Microservices behind one API gateway

- **Status:** accepted
- **Date:** 2026-11-12
- **Decided by:** Ali, from the course brief

## Context
13 students build one ML training platform in two weeks. Training is long and heavy, uploads are storage
work, and inference must be fast. A single program would force everyone into the same code and make every
part scale together.

## Decision
Split the platform into services, one per capability, each with its own folder, database schema and
Docker image. All API traffic enters through **one gateway** (port 5810), which checks the login token,
adds `X-User-Id` and `X-Request-Id`, and forwards to the right service. Only the gateway and the portal
are published. Services talk to each other only through their APIs, never through each other's databases.
Long work (training) is asynchronous: `POST /jobs` answers 202 and the job goes on a queue.

## Why
- Each owner can build, test and deploy their part alone, against a written contract.
- Each part scales by its own needs (GPU workers vs fast inference).
- One place for login, request IDs, timeouts and CORS, instead of 8 copies.

## Trade-offs
- More moving parts: network calls can fail, so we need timeouts, 503s, retries and health checks.
- The gateway is a single point of failure; in the cloud it runs as more than one task behind a load balancer.
- Contracts must be agreed up front and changed with care (Contract change issues).
