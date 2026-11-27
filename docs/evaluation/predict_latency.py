"""Test G: prediction latency through the gateway. Owner: Adel.

Sends N predictions, one after the other, to POST /api/v1/predict for the newest model that has a live
(production) version, and prints the time each took as seen by the client: min, median (p50), p95 and max.
The first request is shown apart (it may load the model).

After `make e2e`, the live model is the walk-through's small CIFAR-10-shaped image TEST model (step 10,
`inference-service/app/fixture_model.py`), not a trained model: these numbers are the platform's serving
path (gateway -> inference -> model in memory), not the speed of a real model.

    export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' .env | cut -d= -f2)
    python3 docs/evaluation/predict_latency.py 50      # from the repository root (uses docker compose)

The test image is made by the inference container (`fixture_model.class_image("cat")`), as the walk-through
does. Standard library only. GATEWAY_URL defaults to http://localhost:5810.
"""

import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:5810").rstrip("/")
TOKEN = os.environ.get("DEV_AUTH_TOKEN", "")


def get(path):
    request = urllib.request.Request(GATEWAY + path, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=20) as answer:
        return json.load(answer)


def cat_image():
    code = 'import sys, app.fixture_model as f; sys.stdout.buffer.write(f.class_image("cat"))'
    done = subprocess.run(
        ["docker", "compose", "exec", "-T", "inference-service", "python", "-c", code],
        capture_output=True,
        timeout=180,
    )
    if done.returncode != 0:
        sys.exit("Could not make the test image: " + done.stderr.decode(errors="replace")[-300:])
    return done.stdout


def multipart(model_id, image):
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="model_id"\r\n\r\n{model_id}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="cat.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    return head + image + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def predict(body, content_type):
    request = urllib.request.Request(
        GATEWAY + "/api/v1/predict",
        data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": content_type},
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:
            result = json.load(answer)
            status = answer.status
    except urllib.error.HTTPError as error:
        result, status = {}, error.code
    return (time.perf_counter() - start) * 1000, status, result


def main():
    if not TOKEN:
        sys.exit("Set DEV_AUTH_TOKEN (see the docstring).")
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    live = [m for m in get("/api/v1/models")["items"] if m.get("production_version")]
    if not live:
        sys.exit("No model has a live version: run `make e2e` first (steps 9-11).")
    model = max(live, key=lambda m: m["created_at"])
    live_version = model["production_version"]
    print(f"Model {model['model_id']} ({model['name']}), live version {live_version}, {count} requests")
    body, content_type = multipart(model["model_id"], cat_image())

    first_ms, status, result = predict(body, content_type)
    top = (result.get("predictions") or [{}])[0].get("label")
    print(f"first request: {first_ms:.1f} ms, HTTP {status}, top label {top}")

    times, failures = [], 0
    for _ in range(count):
        ms, status, _ = predict(body, content_type)
        if status == 200:
            times.append(ms)
        else:
            failures += 1
    print(f"{len(times)} of {count} answered 200, {failures} failed")
    if times:
        p95 = statistics.quantiles(times, n=20, method="inclusive")[-1] if len(times) > 1 else times[0]
        print(
            f"latency ms: min {min(times):.1f}, p50 {statistics.median(times):.1f}, "
            f"p95 {p95:.1f}, max {max(times):.1f}"
        )


if __name__ == "__main__":
    main()
