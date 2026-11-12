"""Sending messages to the SQS queues (LocalStack on a laptop, AWS SQS in the cloud)."""

import json
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

QUEUE_ERRORS = (BotoCoreError, ClientError)


class Queues:
    def __init__(self) -> None:
        self.client = boto3.client(
            "sqs",
            endpoint_url=os.environ.get("SQS_ENDPOINT") or None,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        self.names = {
            "training-jobs": os.environ.get("TRAINING_JOBS_QUEUE", "training-jobs"),
            "job-events": os.environ.get("JOB_EVENTS_QUEUE", "job-events"),
        }
        self._urls: dict[str, str] = {}

    def url(self, queue: str) -> str:
        if queue not in self._urls:
            self._urls[queue] = self.client.get_queue_url(QueueName=self.names[queue])["QueueUrl"]
        return self._urls[queue]

    def send(self, queue: str, body: dict) -> None:
        self.client.send_message(QueueUrl=self.url(queue), MessageBody=json.dumps(body))

    def ready(self) -> bool:
        try:
            for queue in self.names:
                self.url(queue)
        except QUEUE_ERRORS:
            return False
        return True
