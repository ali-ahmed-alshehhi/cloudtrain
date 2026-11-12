# 0002 — Notifications live in the portal, not in a separate service

- **Status:** accepted
- **Date:** 2026-11-12
- **Decided by:** Ali

## Context
The brief lists a Notification service among the 8 logical services. Every student already owns a part,
and job status is already shown by the portal.

## Decision
No separate notification container. Training Jobs stores every status change as an event and publishes it
to the `job-events` queue. The portal's **alert feed** reads recent events with
`GET /api/v1/jobs/events?after=<event_id>` every 5–10 seconds (with back-off), and the monitoring stack
reads `job-events` for dashboards.

## Why
No owner is free for a separate service, and the portal already shows job status.

## Trade-offs
Alerts appear in the portal only, not by email or chat.

## Upgrade path
A small consumer of `job-events` can be added later (e.g. sending email through Amazon SES). Note that
`job-events` has one reader today (monitoring), so a second consumer would need its own queue fed from the
same events (for example an SNS topic fanning out to two queues) — a contract change.
