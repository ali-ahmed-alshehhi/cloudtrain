# Test C: gateway speed, dataset upload/download speed, the service-down alert (raw results)

**Measured:** Fri 20 Nov 2026, 22:50–23:07 (UTC+4), by Adel on a MacBook Pro (Docker Desktop, 7.7 GiB for containers).
**Versions:** branch `adel/job-events-monitor` at `aa6cc8b` (= `main` at `474a732` + #115, the monitoring stack, not merged yet),
Docker Compose v5.6.1. All 15 containers healthy (`make up`). Settings: `.env.example`.
Every request goes through the gateway (port 5810) with the local dev login; commands read it from `.env`:

```bash
TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2); H="Authorization: Bearer $TOKEN"
```

## 1. Gateway speed per route (p50 / p95)

Load: `make e2e` 3 times in a row (21 passed, 8 skipped each: other students' steps; 5.59 s, 5.49 s, 5.51 s).
Then, from the gateway's own histogram (`route!="gateway"` leaves out its health checks):

```bash
docker compose exec prometheus promtool query instant http://localhost:9090 'sum by (route) (increase(gateway_request_duration_seconds_count{route!="gateway"}[15m]))'
docker compose exec prometheus promtool query instant http://localhost:9090 'histogram_quantile(0.50, sum by (le, route) (increase(gateway_request_duration_seconds_bucket{route!="gateway"}[15m])))'
docker compose exec prometheus promtool query instant http://localhost:9090 'histogram_quantile(0.95, sum by (le, route) (increase(gateway_request_duration_seconds_bucket{route!="gateway"}[15m])))'
```

```
{route="experiments"} => 25.625458302779812     p50 0.0075000000000000015   p95 0.049999999999999996
{route="projects"}    => 10.250183321111924     p50 0.0028571428571428576   p95 0.018999999999999996
{route="datasets"}    => 10.250183321111924     p50 0.007                   p95 0.018999999999999996
{route="jobs"}        => 29.469277048196783     p50 0.0077083333333333335   p95 0.022125
```

| Route | Requests (≈) | p50 | p95 |
|---|---|---|---|
| projects | 10 | 2.9 ms | 19 ms |
| datasets | 10 | 7.0 ms | 19 ms |
| jobs | 29 | 7.7 ms | 22 ms |
| experiments (MLflow) | 26 | 7.5 ms | 50 ms |

How to read it: the histogram has buckets at 5, 10, 25, 50 ms…, so each value is an estimate inside its bucket
(experiments p95 = "between 25 and 50 ms"). Counts are not whole numbers because `increase()` extrapolates over 15 minutes.
Small sample (about 75 requests; 10 per route, so p95 is the slowest one or two). The time includes the service behind the gateway.

## 2. Dataset upload and download through the gateway

Files: random bytes packed with `zip -0` (no compression), 50 MiB and 500 MiB. Each run: upload as a new dataset
(`POST /api/v1/datasets`, `format=zip`), then download version 1. Project `project-11` ("Speed test").

```bash
speed() {
  for i in 1 2 3; do
    out=$(curl -s -o /tmp/speed/resp.json -w "%{http_code} %{time_total}s %{size_upload} bytes" -X POST -H "$H" -F project_id=$P -F name="speed $1 $i" -F format=zip -F file=@/tmp/speed/$1 http://localhost:5810/api/v1/datasets)
    D=$(sed -E 's/.*"dataset_id":"([^"]+)".*/\1/' /tmp/speed/resp.json)
    echo "$1 upload $i: $out"
    curl -s -o /dev/null -w "$1 download $i: %{http_code} %{time_total}s %{size_download} bytes\n" -H "$H" http://localhost:5810/api/v1/datasets/$D/versions/1/download
  done
}
speed d50.zip; speed d500.zip
```

```
d50.zip upload 1: 201 0.360157s 52429500 bytes
d50.zip download 1: 200 0.207223s 52428956 bytes
d50.zip upload 2: 201 0.326167s 52429500 bytes
d50.zip download 2: 200 0.226090s 52428956 bytes
d50.zip upload 3: 201 0.323880s 52429500 bytes
d50.zip download 3: 200 0.205214s 52428956 bytes
d500.zip upload 1: 201 3.441386s 524288704 bytes
d500.zip download 1: 200 1.943029s 524288158 bytes
d500.zip upload 2: 201 3.301864s 524288704 bytes
d500.zip download 2: 200 1.898584s 524288158 bytes
d500.zip upload 3: 201 3.413849s 524288704 bytes
d500.zip download 3: 200 1.981179s 524288158 bytes
```

| File | Upload (3 runs) | Upload median | Download (3 runs) | Download median |
|---|---|---|---|---|
| 52.4 MB | 146, 161, 162 MB/s | **161 MB/s** | 253, 232, 256 MB/s | **253 MB/s** |
| 524.3 MB | 152, 159, 154 MB/s | **154 MB/s** | 270, 276, 265 MB/s | **270 MB/s** |

MB = 10^6 bytes, file size ÷ total time. Every download returned exactly the file's size. Upload includes the
format check and the write to S3. Memory after the 500 MB runs: LocalStack 265 MiB, dataset-service 96 MiB.
Everything stays on one laptop (no network), so these are upper bounds, not cloud numbers.

## 3. Alert `CloudTrainServiceDown` (Projects stopped)

Rule: `up{job="cloudtrain"} == 0` for 1 minute; Prometheus scrapes and evaluates every 15 s.

```bash
docker compose stop project-service; start=$(date +%s); echo "stopped at $(date +%T)"
while true; do
  s=$(docker compose exec -T prometheus promtool query instant http://localhost:9090 'ALERTS{alertname="CloudTrainServiceDown"}' | grep -o 'alertstate="[a-z]*"')
  echo "$(( $(date +%s) - start ))s: ${s:-no alert yet}"
  [[ "$s" == *firing* ]] && break
  sleep 5
done
# then the same loop after: docker compose start project-service (until the alert is gone)
```

```
stopped at 23:03:44
1s … 26s: no alert yet
31s … 83s: alertstate="pending"
88s: alertstate="firing"
started at 23:06:45
0s … 26s: alertstate="firing"
31s: alert cleared
```

| Moment | After the change | Expected from the rule |
|---|---|---|
| Pending | 26–31 s | up to 30 s (next scrape + next evaluation) |
| Firing | 83–88 s | pending + 60 s, so up to 90 s |
| Cleared after restart | 26–31 s | start-up + next scrape + next evaluation |

Times are within the 5 s polling of the loop.
