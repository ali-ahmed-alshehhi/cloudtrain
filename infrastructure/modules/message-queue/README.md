# Module: message-queue

Owners: Hamda + Fatma.

SQS queues `training-jobs` (dead-letter redrive to `training-jobs-dlq`) and `job-events`, encrypted; visibility timeout covers scheduling time (default 300s).
`training-jobs-dlq` keeps messages for **14 days** (SQS maximum) so failed-for-good reports survive a weekend.
Implemented in `main.tf`.

