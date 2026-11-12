#!/bin/bash
# LocalStack start-up script (local only). LocalStack runs it when it is ready.
# Creates what AWS will have in the cloud (made by Terraform there):
#   - S3 buckets: datasets, artifacts
#   - SQS queues: training-jobs (a message that fails SQS_MAX_RECEIVE_COUNT times moves to
#     training-jobs-dlq), training-jobs-dlq, job-events — all encrypted
# LocalStack keeps everything in memory: after a restart this script creates them again, empty.
set -euo pipefail

awslocal s3 mb "s3://$DATASETS_BUCKET"
awslocal s3 mb "s3://$ARTIFACTS_BUCKET"

awslocal sqs create-queue --queue-name "$TRAINING_JOBS_DLQ" --attributes SqsManagedSseEnabled=true
awslocal sqs create-queue --queue-name "$JOB_EVENTS_QUEUE" --attributes SqsManagedSseEnabled=true

# The settings of training-jobs, written as JSON (SQS wants the redrive policy as a JSON string).
export DLQ_ARN="arn:aws:sqs:$AWS_REGION:000000000000:$TRAINING_JOBS_DLQ"
attributes=$(python3 -c '
import json, os
redrive = {"deadLetterTargetArn": os.environ["DLQ_ARN"], "maxReceiveCount": os.environ["SQS_MAX_RECEIVE_COUNT"]}
print(json.dumps({
    "VisibilityTimeout": os.environ["SQS_VISIBILITY_TIMEOUT_SECONDS"],
    "RedrivePolicy": json.dumps(redrive),
    "SqsManagedSseEnabled": "true",
}))')
awslocal sqs create-queue --queue-name "$TRAINING_JOBS_QUEUE" --attributes "$attributes"

echo "CloudTrain buckets and queues are ready"
