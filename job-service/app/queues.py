"""The SQS queues (LocalStack on a laptop, AWS SQS in the cloud).

This service WRITES `training-jobs` (the job form) and `job-events` (every status change), and
READS `training-jobs-dlq` (contracts: one reader per queue). Tests replace this class with a fake.
"""

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
            "training-jobs-dlq": os.environ.get("TRAINING_JOBS_DLQ", "training-jobs-dlq"),
        }
        self._urls: dict[str, str] = {}

    def url(self, queue: str) -> str:
        if queue not in self._urls:
            self._urls[queue] = self.client.get_queue_url(QueueName=self.names[queue])["QueueUrl"]
        return self._urls[queue]

    def send(self, queue: str, body: dict) -> None:
        self.client.send_message(QueueUrl=self.url(queue), MessageBody=json.dumps(body))

    def receive(self, queue: str, wait_seconds: int) -> list[dict]:
        """Up to 10 messages: [{"body": {...}, "receipt": "..."}]. Waits up to wait_seconds."""
        answer = self.client.receive_message(
            QueueUrl=self.url(queue), MaxNumberOfMessages=10, WaitTimeSeconds=wait_seconds
        )
        found = []
        for message in answer.get("Messages", []):
            try:
                body = json.loads(message["Body"])
            except ValueError:
                body = {"unreadable": message["Body"][:200]}
            found.append({"body": body, "receipt": message["ReceiptHandle"]})
        return found

    def delete(self, queue: str, receipt: str) -> None:
        self.client.delete_message(QueueUrl=self.url(queue), ReceiptHandle=receipt)

    def hide(self, queue: str, receipt: str, seconds: int) -> None:
        """Leave a message on the queue but do not show it to us again for `seconds`."""
        self.client.change_message_visibility(
            QueueUrl=self.url(queue), ReceiptHandle=receipt, VisibilityTimeout=seconds
        )

    def ready(self) -> bool:
        try:
            for queue in self.names:
                self.url(queue)
        except QUEUE_ERRORS:
            return False
        return True
