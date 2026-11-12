# CloudTrain Training Jobs service image (stand-in).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

# Install libraries first, so this layer is reused when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a normal user, not root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# 8003 is this service's port in the contract (contracts/ports.md).
EXPOSE 8003
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8003"]
