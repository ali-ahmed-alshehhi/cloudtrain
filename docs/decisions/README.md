# Decisions (ADRs)

One short file per important decision, numbered in order: `NNNN-short-title.md`.
Each one says: **context** (the problem), **decision**, **why**, **trade-offs**.

Write one when you change a default (portal framework, login provider, EC2 vs Batch), change a contract,
or make a choice others must live with. Copy the shape of `0001-microservices-and-gateway.md`.

| # | Decision | Status |
|---|---|---|
| 0001 | Microservices behind one API gateway | accepted |
| 0002 | Notifications live in the portal | accepted |
| 0003 | Node 24 instead of Node 20 | accepted |
| 0004 | Public GitHub repository | accepted (instructors to confirm) |
| 0005 | LocalStack S3 instead of MinIO on laptops | accepted |
| 0006 | Amazon Cognito as the login provider | accepted |
