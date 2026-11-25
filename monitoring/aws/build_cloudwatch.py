# ruff: noqa: E501  (metric definitions read better on one line)
"""Builds cloudwatch-dashboard.json.tftpl (owners: Hilal + Adel, Student 10). Proposal: #109 item 2.

For Hamda + Fatma's `infrastructure/modules/monitoring`:
    resource "aws_cloudwatch_dashboard" "cloudtrain" {
      dashboard_name = "cloudtrain"
      dashboard_body = templatefile("${path.root}/../monitoring/aws/cloudwatch-dashboard.json.tftpl", {...})
    }
Template variables: region, training_jobs_queue, training_jobs_dlq, job_events_queue, alb_arn_suffix, ecs_cluster_name.
Run:  python3 monitoring/aws/build_cloudwatch.py
"""

import json
from pathlib import Path

OUT = Path(__file__).parent / "cloudwatch-dashboard.json.tftpl"
NS = "CloudTrain"  # namespace of the EMF lines written by job-events-monitor (app/metrics.py)
SVC = ["Service", "job-events-monitor"]
# Every event type in the contract, read from the schema so the dashboard never misses one.
SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "events" / "job-event.schema.json"
EVENT_TYPES = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"]["event_type"]["enum"]
RESULTS = ["SUCCEEDED", "FAILED", "CANCELLED"]

widgets: list[dict] = []
_pos = {"x": 0, "y": 0}


def place(width: int, height: int) -> dict:
    if _pos["x"] + width > 24:
        _pos["x"], _pos["y"] = 0, _pos["y"] + 6
    spot = {"x": _pos["x"], "y": _pos["y"], "width": width, "height": height}
    _pos["x"] += width
    return spot


def text(markdown: str, width: int = 24, height: int = 2) -> None:
    widgets.append({"type": "text", **place(width, height), "properties": {"markdown": markdown}})
    _pos["x"], _pos["y"] = 0, _pos["y"] + height


def chart(
    title: str,
    metrics: list,
    stat: str = "Average",
    period: int = 300,
    width: int = 8,
    view: str = "timeSeries",
    unit_label: str | None = None,
) -> None:
    props = {
        "title": title,
        "region": "${region}",
        "view": view,
        "stacked": False,
        "stat": stat,
        "period": period,
        "metrics": metrics,
    }
    if unit_label:
        props["yAxis"] = {"left": {"label": unit_label, "min": 0}}
    widgets.append({"type": "metric", **place(width, 6), "properties": props})


text(
    "## CloudTrain\nJob metrics from **job-events-monitor** (CloudWatch EMF, namespace `CloudTrain`), queues, load balancer and containers. On the AWS Emulator (decision 0011) this dashboard is created but receives no live data; the live dashboard is the local Grafana."
)

chart(
    "Job events (count)",
    [[NS, "JobEvents", *SVC, "EventType", t, {"label": t}] for t in EVENT_TYPES],
    stat="Sum",
    unit_label="events",
)
chart(
    "Waiting in the queue (QUEUED → RUNNING)",
    [
        [NS, "QueueWaitSeconds", *SVC, {"stat": "Average", "label": "average"}],
        [NS, "QueueWaitSeconds", *SVC, {"stat": "p95", "label": "p95"}],
    ],
    unit_label="seconds",
)
chart(
    "Training time by result (RUNNING → end)",
    [[NS, "RunSeconds", *SVC, "Result", r, {"label": r}] for r in RESULTS],
    unit_label="seconds",
)

chart(
    "Messages waiting",
    [
        ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", q, {"label": q}]
        for q in ("${training_jobs_queue}", "${training_jobs_dlq}", "${job_events_queue}")
    ],
    stat="Maximum",
    period=60,
    unit_label="messages",
)
chart(
    "Oldest message age",
    [
        ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", q, {"label": q}]
        for q in ("${training_jobs_queue}", "${job_events_queue}")
    ],
    stat="Maximum",
    period=60,
    unit_label="seconds",
)
chart(
    "job-events delay (occurred → read), p95",
    [[NS, "EventLagSeconds", *SVC, {"stat": "p95", "label": "p95"}]],
    unit_label="seconds",
)

chart(
    "Load balancer: server errors and requests",
    [
        [
            "AWS/ApplicationELB",
            "HTTPCode_Target_5XX_Count",
            "LoadBalancer",
            "${alb_arn_suffix}",
            {"label": "5xx", "stat": "Sum"},
        ],
        [
            "AWS/ApplicationELB",
            "RequestCount",
            "LoadBalancer",
            "${alb_arn_suffix}",
            {"label": "requests", "stat": "Sum"},
        ],
    ],
    stat="Sum",
    period=60,
)
chart(
    "Load balancer: answer time p95",
    [
        [
            "AWS/ApplicationELB",
            "TargetResponseTime",
            "LoadBalancer",
            "${alb_arn_suffix}",
            {"stat": "p95", "label": "p95"},
        ]
    ],
    period=60,
    unit_label="seconds",
)
chart(
    "Containers: CPU and memory",
    [
        ["AWS/ECS", "CPUUtilization", "ClusterName", "${ecs_cluster_name}", {"label": "CPU %"}],
        ["AWS/ECS", "MemoryUtilization", "ClusterName", "${ecs_cluster_name}", {"label": "memory %"}],
    ],
    period=60,
    unit_label="percent",
)

OUT.write_text(json.dumps({"widgets": widgets}, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(widgets)} widgets)")
