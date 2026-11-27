# Official AWS Emulator (Student 6 practice account).
# Docs: https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html
# Source: https://github.com/aws/aws-emulator
#
# Build (from infrastructure/):
#   docker compose -f docker-compose.emulator.yml build

FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal

ARG TARGETARCH
# Pinned, so a new emulator release cannot change our tests overnight. With "latest" (1.0.611 on 25 Nov)
# the Login workflow's real Cognito tokens were refused (issuer); 1.0.604 is the last green run's version.
# Versions: https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/versions.json
ARG EMULATOR_VERSION=1.0.604

RUN case "${TARGETARCH}" in \
      arm64) ARCH=aarch64 ;; \
      amd64|x86_64) ARCH=x86_64 ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && curl -fsSL -o /tmp/aws-emulator.rpm \
      "https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/aws-emulator-${EMULATOR_VERSION}-1-${ARCH}.rpm" \
 && rpm -i /tmp/aws-emulator.rpm \
 && rm /tmp/aws-emulator.rpm \
 && mkdir -p /home/emulator \
 && chown 1000 /home/emulator

USER 1000
ENV HOME=/home/emulator
EXPOSE 9297
# Listen on all interfaces inside the container so Docker can publish the port.
# Telemetry off for classroom machines.
ENTRYPOINT ["aws-emulator", "-b", "0.0.0.0", "--telemetry", "off"]
