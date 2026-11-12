# The contract tester used by `make contract`. It joins the docker-compose network, so it can reach
# every service directly (only the gateway and portal are published to the laptop).
FROM python:3.11-slim

RUN pip install --no-cache-dir schemathesis==4.33.2

WORKDIR /contract-tests
# Schemathesis reads schemathesis.toml from the folder it runs in.
COPY schemathesis.toml run.sh ./
CMD ["bash", "run.sh"]
