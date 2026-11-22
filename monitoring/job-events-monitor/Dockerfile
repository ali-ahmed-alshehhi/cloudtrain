# CloudTrain job-events-monitor image (owners: Hilal + Adel, Student 10).
# Build outside Compose: docker build --build-context contracts=contracts monitoring/job-events-monitor
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

# Install libraries first, so this layer is reused when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# The event contract, built in, because nothing is mounted in the cloud (JOB_EVENT_SCHEMA).
COPY --from=contracts events/job-event.schema.json /contracts/events/job-event.schema.json

# Run as a normal user, not root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# 8011: proposed in #109 (not published; Prometheus scrapes it inside the Docker network).
EXPOSE 8011
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8011"]
