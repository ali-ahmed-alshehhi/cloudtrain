# Test A: a service stopped or frozen (raw results)

**Measured:** Thu 19 Nov 2026, 09:10–09:18 (UTC+4), by Adel on a MacBook Pro.
**Versions:** Git `f8d8dab` (`main`), Docker Compose v5.6.1, all 12 containers healthy after `make up`.
**Settings:** `.env.example` unchanged (`GATEWAY_TIMEOUT_SECONDS=10`).
**Service used:** `project-service`, route `GET /api/v1/projects` through the gateway (port 5810).

Every request:

```bash
DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)  # the local-only login from .env
curl -s -o /dev/null -w "%{http_code} in %{time_total}s\n" \
  -H "Authorization: Bearer $DEV_AUTH_TOKEN" http://localhost:5810/api/v1/projects
```

## 1. Normal (baseline), 5 requests

```
200 in 0.024416s
200 in 0.007338s
200 in 0.007213s
200 in 0.005251s
200 in 0.005028s
```

## 2. Stopped (`docker compose stop project-service`), 5 requests

```
503 in 0.042241s
503 in 0.004114s
503 in 0.003759s
503 in 0.004189s
503 in 0.004120s
```

Body: `{"error":{"code":"SERVICE_UNAVAILABLE","message":"projects is not reachable","request_id":"req-01f3dd17"}}`
Gateway `GET /health` at the same time: `200`.

## 3. Frozen (`docker compose start`, wait 10 s, `docker compose pause project-service`), 3 requests

The container is running but does not answer, like a stuck service.

```
503 in 10.011705s
503 in 10.012939s
503 in 10.012622s
```

The body was not captured in this run. The gateway code for a timeout is `gateway/app/proxy.py`
(`SERVICE_UNAVAILABLE`, "projects did not answer in time").

## 4. Recovered (`docker compose unpause project-service`), 3 requests right after

```
200 in 0.005774s
200 in 0.003889s
200 in 0.004744s
```

No gateway restart was needed: the first request after `unpause` already succeeded.

## Summary (median, range)

| Case | Answer | Median | Range |
|---|---|---|---|
| Normal | 200 × 5 | 7.2 ms | 5.0–24.4 ms |
| Stopped | 503 × 5 | 4.1 ms | 3.8–42.2 ms |
| Frozen | 503 × 3 | 10.013 s | 10.012–10.013 s (= the 10 s timeout) |
| Recovered | 200 × 3 | 4.7 ms | 3.9–5.8 ms |

The first request of a series is the slowest (new connection). Laptop numbers, not production numbers.
