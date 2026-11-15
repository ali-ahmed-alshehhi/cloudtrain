"""gpu_hours and estimated_cost_usd from contracts/pricing.yaml (placeholder prices for now)."""

from tests.conftest import FORM, beat, job, report, start, submit, sweep

ONE_GPU = {
    **FORM,
    "resources": {"gpu_count": 1, "cpu_cores": 4, "memory_gb": 16},
    "parallelism": {"strategy": "single", "world_size": 1},
}


def test_a_queued_job_costs_nothing(client):
    found = submit(client)
    assert (found["gpu_hours"], found["estimated_cost_usd"]) == (0, 0)


def test_cost_of_a_finished_job(client, clock):
    job_id = submit(client, ONE_GPU)["job_id"]
    start(client, job_id, machine_type="g4dn.xlarge")  # 0.53 USD an hour (placeholder)
    clock.advance(30 * 60)

    done = report(client, job_id, "SUCCEEDED", reported_by="worker").json()

    assert done["gpu_hours"] == 0.5
    assert done["estimated_cost_usd"] == 0.265


def test_a_running_job_shows_its_cost_so_far(client, clock):
    job_id = submit(client)["job_id"]  # 2 GPUs
    start(client, job_id, machine_type="g4dn.12xlarge")  # 3.91 USD an hour (placeholder)
    clock.advance(15 * 60)
    beat(client, job_id)

    found = job(client, job_id)

    assert found["gpu_hours"] == 0.5  # 2 GPUs x 0.25 hours
    assert found["estimated_cost_usd"] == 0.9775


def test_a_failed_attempt_still_counts(client, clock):
    """The machine of the failed attempt was paid for, so the job's cost includes it."""
    job_id = submit(client, ONE_GPU)["job_id"]
    start(client, job_id, machine_type="g4dn.xlarge")
    clock.advance(121)
    sweep(client)  # attempt 1 fails after 121 seconds of silence
    start(client, job_id, machine_type="g4dn.xlarge")
    clock.advance(3600 - 121)

    done = report(client, job_id, "SUCCEEDED", reported_by="worker").json()

    assert done["gpu_hours"] == 1.0
    assert done["estimated_cost_usd"] == 0.53


def test_a_machine_missing_from_pricing_is_free_not_an_error(client, clock):
    job_id = submit(client, ONE_GPU)["job_id"]
    start(client, job_id, machine_type="p5.48xlarge")
    clock.advance(3600)

    done = report(client, job_id, "SUCCEEDED", reported_by="worker").json()

    assert done["gpu_hours"] == 1.0
    assert done["estimated_cost_usd"] == 0
