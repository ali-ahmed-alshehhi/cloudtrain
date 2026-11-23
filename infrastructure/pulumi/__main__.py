"""Pulumi layer above Terraform: reads Terraform's outputs, creates one CloudWatch dashboard.

Terraform owns every other resource. This program never changes a Terraform resource, and
Terraform never reads from it. Run after `terraform apply`; destroy before `terraform destroy`.
"""

import json
import os

import pulumi
import pulumi_aws as aws

config = pulumi.Config()
environment = config.get("environment") or "dev"
region = config.get("region") or "us-east-1"
use_emulator = config.get_bool("useEmulator") or False
emulator_endpoint = config.get("emulatorEndpoint") or "https://127.0.0.1:9297"

# `terraform output -json > tf-outputs.json` (path from config or TF_OUTPUTS_FILE)
outputs_file = config.get("terraformOutputsFile") or os.environ.get("TF_OUTPUTS_FILE", "tf-outputs.json")
with open(outputs_file, encoding="utf-8") as f:
    tf = {name: item["value"] for name, item in json.load(f).items()}


def queue_name(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


provider = aws.Provider(
    "aws",
    region=region,
    skip_credentials_validation=use_emulator,
    skip_requesting_account_id=use_emulator,
    skip_metadata_api_check=use_emulator,
    endpoints=[aws.ProviderEndpointArgs(cloudwatch=emulator_endpoint)] if use_emulator else None,
    default_tags=aws.ProviderDefaultTagsArgs(
        tags={
            "Project": "cloudtrain",
            "Environment": environment,
            "Owner": "hamda-fatma",
            "ManagedBy": "pulumi",
        }
    ),
)

jobs_q = queue_name(tf["training_jobs_queue_url"])
dlq = queue_name(tf["training_jobs_dlq_url"])
events_q = queue_name(tf["job_events_queue_url"])
alb = tf.get("alb_arn_suffix")
cluster = tf.get("ecs_cluster_name")
pools = [
    g
    for g in (
        tf.get("gpu_worker_autoscaling_group"),
        tf.get("multi_gpu_worker_autoscaling_group"),
    )
    if g
]


def widget(title, metrics, x, y, stat="Maximum"):
    return {
        "type": "metric",
        "x": x,
        "y": y,
        "width": 12,
        "height": 6,
        "properties": {
            "title": title,
            "region": region,
            "stat": stat,
            "period": 60,
            "view": "timeSeries",
            "metrics": metrics,
        },
    }


sqs_visible = "ApproximateNumberOfMessagesVisible"
sqs_age = "ApproximateAgeOfOldestMessage"
asg_in_service = "GroupInServiceInstances"

widgets = [
    widget(
        "Messages waiting",
        [["AWS/SQS", sqs_visible, "QueueName", q] for q in (jobs_q, dlq, events_q)],
        0,
        0,
    ),
    widget(
        "Oldest message (s)",
        [["AWS/SQS", sqs_age, "QueueName", q] for q in (jobs_q, events_q)],
        12,
        0,
    ),
    widget(
        "GPU workers running",
        [["AWS/AutoScaling", asg_in_service, "AutoScalingGroupName", g] for g in pools],
        0,
        6,
    ),
]
if alb:
    widgets.append(
        widget(
            "Load balancer: requests and 5xx",
            [
                ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", alb],
                ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", alb],
                ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", alb],
            ],
            12,
            6,
            stat="Sum",
        )
    )
if cluster:
    widgets.append(
        widget(
            "ECS CPU and memory (%)",
            [
                ["AWS/ECS", "CPUUtilization", "ClusterName", cluster],
                ["AWS/ECS", "MemoryUtilization", "ClusterName", cluster],
            ],
            0,
            12,
            stat="Average",
        )
    )

dashboard = aws.cloudwatch.Dashboard(
    "cloudtrain",
    dashboard_name=f"{environment}-cloudtrain",
    dashboard_body=json.dumps({"widgets": widgets}),
    opts=pulumi.ResourceOptions(provider=provider),
)

pulumi.export("dashboard_name", dashboard.dashboard_name)
pulumi.export("widget_count", len(widgets))
