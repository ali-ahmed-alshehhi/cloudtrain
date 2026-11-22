# Test G: prediction latency through the gateway (raw results)

**Measured:** Sun 22 Nov 2026, about 15:10 (UTC+4), by Adel on the laptop in section 0 of `EVALUATION.md`.
**Versions:** `main` at `1bb2326` (prediction from #150). All 15 containers healthy after `make up`;
`make e2e` 25 passed, 4 skipped (steps 9–11, register, promote and predict, passed).
**Model:** `model-02` (`cifar10-classifier`), live version 1: the walk-through's small CIFAR-10-shaped image
**test model** (`inference-service/app/fixture_model.py`, step 10), not a trained model. So these numbers are the
platform's serving path (gateway → inference service → a small model already in memory), not the speed of a
real model.

## Commands

```bash
make up && make e2e
export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
python3 docs/evaluation/predict_latency.py 100
```

[`predict_latency.py`](predict_latency.py) sends one request first (shown apart), then 100 more, one after the
other, each `POST /api/v1/predict` with the same cat PNG (made by the inference container, as the walk-through
does) and `model_id`. Times are measured by the client, from sending the request to reading the answer.

## Output

```
Model model-02 (cifar10-classifier), live version 1, 100 requests
first request: 9.5 ms, HTTP 200, top label cat
100 of 100 answered 200, 0 failed
latency ms: min 2.6, p50 3.2, p95 4.4, max 6.1
```

## Summary

| Measure | Result |
|---|---|
| Answers | **100 of 100** HTTP 200; the top label of the first answer is `cat` |
| Latency (client, through the gateway) | min **2.6 ms**, p50 **3.2 ms**, p95 **4.4 ms**, max **6.1 ms** |
| First request | 9.5 ms (the model version was already loaded by step 10's health gate) |

**What it means.** The platform adds only a few milliseconds around a prediction on one laptop: the gateway's
check and forwarding, the inference service and its answer. A trained model would add its own compute time on
top, and in the cloud the network to the load balancer would add more. One client sending one request at a
time: this is not a load test.
