# MLflow tracking server: the OFFICIAL image, plus the libraries it needs to talk to
# PostgreSQL (psycopg), S3 (boto3) and to serve /metrics (prometheus-flask-exporter).
# No CloudTrain code here — configuration only.
# Owner: Abdullah.
FROM ghcr.io/mlflow/mlflow:v3.18.0

RUN pip install --no-cache-dir "psycopg[binary]==3.3.8" boto3==1.44.1 prometheus-flask-exporter==0.23.2

# Settings come from environment variables (docker-compose.yml / .env):
#   MLFLOW_DATABASE_URL      runs and registry, in the PostgreSQL schema `mlflow`
#   ARTIFACTS_BUCKET         models and run files go to s3://$ARTIFACTS_BUCKET/mlflow
#   MLFLOW_S3_ENDPOINT_URL   LocalStack S3 locally (empty = real AWS S3)
# --allowed-hosts: MLflow refuses requests addressed to names it does not know; these are the
#   names it is called by inside the Docker network and on the laptop.
# --expose-prometheus: turns on GET /metrics (shared rule for every service).
EXPOSE 5000
CMD ["sh", "-c", "exec mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri \"$MLFLOW_DATABASE_URL\" \
  --artifacts-destination \"s3://$ARTIFACTS_BUCKET/mlflow\" --serve-artifacts \
  --allowed-hosts \"mlflow,mlflow:5000,localhost,localhost:5000\" \
  --expose-prometheus /tmp/mlflow-metrics"]
