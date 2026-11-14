"""Pick a machine type for a job based on its gpu_count."""

import os

LOCAL_MACHINE = "local-cpu"

# Cloud machine types from contracts/pricing.yaml.
# Locally the scheduler always uses local-cpu regardless of gpu_count.
CLOUD_MACHINES = {
    0: "c6i.2xlarge",
    1: "g4dn.xlarge",
    4: "g4dn.12xlarge",
}


def pick_machine(gpu_count: int) -> str:
    """Return the machine type string for a job that needs this many GPUs.

    Locally (ENVIRONMENT=local, the default) every job runs on local-cpu.
    In the cloud, 0 GPUs gets a CPU instance, 1 GPU gets g4dn.xlarge,
    and 2-4 GPUs get g4dn.12xlarge (the smallest type with enough GPUs).
    """
    if os.environ.get("ENVIRONMENT", "local") == "local":
        return LOCAL_MACHINE

    if gpu_count <= 0:
        return CLOUD_MACHINES[0]
    if gpu_count <= 1:
        return CLOUD_MACHINES[1]
    return CLOUD_MACHINES[4]
