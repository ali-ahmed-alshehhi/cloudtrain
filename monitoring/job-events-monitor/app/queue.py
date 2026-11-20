"""The job-events SQS queue (LocalStack on a laptop, AWS SQS in the cloud).

This service is the ONLY reader of `job-events` (contracts: one reader per queue; docs/ARCHITECTURE.md).
It needs exactly three permissions on that one queue: ReceiveMessage, DeleteMessage, GetQueueUrl.
Tests replace this class with a fake, or run it against moto.
"""

from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

QUEUE_ERRORS = (BotoCoreError, ClientError)


@dataclass(frozen=True)
class Message:
    body: str
    receipt: str


class JobEventsQueue:
    def __init__(self, name: str, endpoint: str | None, region: str, client=None) -> None:
        self.name = name
        self.client = client or boto3.client("sqs", endpoint_url=endpoint, region_name=region)
        self._url: str | None = None

    def url(self) -> str:
        if self._url is None:
            self._url = self.client.get_queue_url(QueueName=self.name)["QueueUrl"]
        return self._url

    def receive(self, wait_seconds: int) -> list[Message]:
        """Up to 10 messages, waiting up to wait_seconds for the first one (long polling)."""
        answer = self.client.receive_message(
            QueueUrl=self.url(), MaxNumberOfMessages=10, WaitTimeSeconds=wait_seconds
        )
        return [Message(m["Body"], m["ReceiptHandle"]) for m in answer.get("Messages", [])]

    def delete(self, receipt: str) -> None:
        self.client.delete_message(QueueUrl=self.url(), ReceiptHandle=receipt)
