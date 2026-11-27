# Test E: alert delay in the portal (raw results)

**Measured:** Sun 22 Nov 2026, 12:32–12:36 (UTC+4), by Adel on the laptop in section 0 of `EVALUATION.md`.
**Versions:** branch `adel/compare-cost-pages` at `db26b20` (`main` at `0cf0f1c` + the portal pages of #156; the
Projects page and its alerts are #99, unchanged). All 15 containers healthy after `make up`; `make e2e` 22 passed,
7 skipped. Browser: the laptop's Google Chrome, headless (Playwright).
**What is measured:** for each job event, the time from the event (`occurred_at`, set by job-service) until its
alert line is on the Projects page. The page asks the gateway for new events every 5 s
(`portal/lib/alerts/feed.mjs`, `POLL_MS`), so 0–5 s plus the request is expected.

## Commands

```bash
# make up; make e2e (one finished job to copy the dataset from)
cd portal
export PLAYWRIGHT_CHROME_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' ../.env | cut -d= -f2)
node ../docs/evaluation/alert-delay.cjs 10
cd ..
docker compose exec -T prometheus promtool query instant http://localhost:9090 \
  'sum(increase(cloudtrain_job_event_lag_seconds_sum[30m])) / sum(increase(cloudtrain_job_event_lag_seconds_count[30m]))'
```

[`alert-delay.cjs`](alert-delay.cjs) submits 10 small CPU jobs one after the other (the walk-through's job form,
on the dataset of the newest finished walk-through job), after a random 0–5 s pause each, so they start at
different points of the 5 s cycle. It keeps the Projects page open on that project and notes the first moment
each alert line is on the page. *delay* = alert visible − `occurred_at` (laptop clock vs Docker's clock);
*from submit* = alert visible − the moment the script sent `POST /jobs` (one clock).

## Output

```
Project project-53, dataset dataset-58 v1, 10 jobs
run 1: job-18 SUCCEEDED
run 2: job-19 SUCCEEDED
run 3: job-20 SUCCEEDED
run 4: job-21 SUCCEEDED
run 5: job-22 SUCCEEDED
run 6: job-23 SUCCEEDED
run 7: job-24 SUCCEEDED
run 8: job-25 SUCCEEDED
run 9: job-26 SUCCEEDED
run 10: job-27 SUCCEEDED

run  job      event          occurred_at (UTC)          delay s  from submit s
1    job-18   job.queued     2026-11-22T08:32:55.681077Z    1.59           1.62
1    job-18   job.scheduled  2026-11-22T08:32:55.700931Z    1.57           1.62
1    job-18   job.running    2026-11-22T08:32:55.713857Z    1.55           1.62
1    job-18   job.succeeded  2026-11-22T08:32:59.509568Z    2.77           6.64
2    job-19   job.queued     2026-11-22T08:33:14.440362Z    2.89           2.92
2    job-19   job.scheduled  2026-11-22T08:33:14.454474Z    2.88           2.92
2    job-19   job.running    2026-11-22T08:33:14.469749Z    2.86           2.92
2    job-19   job.succeeded  2026-11-22T08:33:18.260280Z    4.09           7.93
3    job-20   job.queued     2026-11-22T08:33:33.407014Z    3.99           4.02
3    job-20   job.scheduled  2026-11-22T08:33:33.427906Z    3.97           4.02
3    job-20   job.running    2026-11-22T08:33:33.438979Z    3.96           4.02
3    job-20   job.succeeded  2026-11-22T08:33:36.820907Z    0.58           4.02
4    job-21   job.queued     2026-11-22T08:33:52.501526Z    4.98           5.00
4    job-21   job.scheduled  2026-11-22T08:33:52.519315Z    4.96           5.00
4    job-21   job.running    2026-11-22T08:33:52.530058Z    4.95           5.00
4    job-21   job.succeeded  2026-11-22T08:33:55.655745Z    1.82           5.00
5    job-22   job.queued     2026-11-22T08:34:10.453558Z    2.06           2.09
5    job-22   job.scheduled  2026-11-22T08:34:10.471076Z    2.05           2.09
5    job-22   job.running    2026-11-22T08:34:10.482583Z    2.04           2.09
5    job-22   job.succeeded  2026-11-22T08:34:13.714489Z    3.82           7.11
6    job-23   job.queued     2026-11-22T08:34:30.271839Z    2.32           2.33
6    job-23   job.scheduled  2026-11-22T08:34:30.282493Z    2.31           2.33
6    job-23   job.running    2026-11-22T08:34:30.294436Z    2.29           2.33
6    job-23   job.succeeded  2026-11-22T08:34:33.511985Z    4.09           7.35
7    job-24   job.queued     2026-11-22T08:34:46.589265Z    1.05           1.06
7    job-24   job.scheduled  2026-11-22T08:34:46.599784Z    1.04           1.06
7    job-24   job.running    2026-11-22T08:34:46.610549Z    1.03           1.06
7    job-24   job.succeeded  2026-11-22T08:34:49.718176Z    2.94           6.09
8    job-25   job.queued     2026-11-22T08:35:05.205169Z    2.51           2.53
8    job-25   job.scheduled  2026-11-22T08:35:05.220481Z    2.49           2.53
8    job-25   job.running    2026-11-22T08:35:05.233509Z    2.48           2.53
8    job-25   job.succeeded  2026-11-22T08:35:08.546442Z    4.19           7.56
9    job-26   job.queued     2026-11-22T08:35:22.244897Z    0.63           0.64
9    job-26   job.scheduled  2026-11-22T08:35:22.255793Z    0.62           0.64
9    job-26   job.running    2026-11-22T08:35:22.266870Z    0.61           0.64
9    job-26   job.succeeded  2026-11-22T08:35:25.966612Z    1.92           5.66
10   job-27   job.queued     2026-11-22T08:35:41.996721Z    0.94           0.96
10   job-27   job.scheduled  2026-11-22T08:35:42.012200Z    0.93           0.96
10   job-27   job.running    2026-11-22T08:35:42.028949Z    0.91           0.96
10   job-27   job.succeeded  2026-11-22T08:35:46.362351Z    1.59           5.98

40 of 40 events shown as alerts; 0 not seen
delay: median 2.30 s, min 0.58 s, max 4.98 s
  job.queued     median 2.19 s (n=10)
  job.scheduled  median 2.18 s (n=10)
  job.running    median 2.16 s (n=10)
  job.succeeded  median 2.86 s (n=10)
submit -> "is queued" alert (one clock): median 2.21 s, max 5.00 s
raw rows: /tmp/alert-delay.json
```

```
{} => 0.005991568181818181 @[1795336793.688]
```

## Summary

| Measure | Result |
|---|---|
| Alerts shown | **40 of 40** events (10 jobs × queued, placed, running, succeeded), none missing |
| Event → alert on the page | median **2.30 s**, 0.58–4.98 s |
| `POST /jobs` → "is queued" alert (one clock) | median **2.21 s**, max **5.00 s** |
| Event → read by `job-events-monitor` | average **6 ms** (`cloudtrain_job_event_lag_seconds`, sum ÷ count of `increase()` over 30 min: a window average, which also includes the `make e2e` job) |

**What it means.** Every delay is inside the 5 s polling interval, and the median is close to half of it (2.5 s),
as expected when events arrive at random points of the cycle. Queued, placed and running come 10–30 ms apart
and show up together, in the same poll. The monitor reads events in milliseconds, so almost all of the delay is
the page's 5 s poll, which the contract allows (5–10 s). Faster alerts would need a shorter poll or a push
channel (not planned). The *delay* column compares the laptop's clock with Docker's; the *from submit* column
uses only the laptop's clock and agrees with it (within 0.03 s for the queued events), so clock drift is not a
concern here.

One laptop, one browser, a small CPU job: these numbers show the portal's alert path, not cloud network latency.
