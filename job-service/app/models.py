"""The training job form, as contracts/training-job.schema.json (POST /jobs sends it without job_id)."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ProjectId = Annotated[str, Field(pattern=r"^project-[0-9]+$")]
DatasetId = Annotated[str, Field(pattern=r"^dataset-[0-9]+$")]


class Hyperparameters(BaseModel):
    model_config = ConfigDict(extra="allow")  # extra settings (e.g. momentum) are allowed

    epochs: int = Field(ge=1, le=1000)
    batch_size: int = Field(ge=1, le=4096)
    learning_rate: float = Field(gt=0, le=10)


class Resources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gpu_count: int = Field(ge=0, le=8)
    cpu_cores: int = Field(ge=1, le=96)
    memory_gb: int = Field(ge=1, le=768)


class Parallelism(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["single", "ddp"]
    world_size: int = Field(ge=1, le=8)


class Execution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_runtime_minutes: int = Field(ge=1, le=1440)
    retry_limit: int = Field(ge=0, le=5)


class JobSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: ProjectId
    dataset_id: DatasetId
    dataset_version: int = Field(ge=1)
    model: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=64)
    hyperparameters: Hyperparameters
    resources: Resources
    parallelism: Parallelism
    execution: Execution

    @model_validator(mode="after")
    def parallelism_matches_resources(self) -> "JobSubmission":
        if self.parallelism.strategy == "single" and self.parallelism.world_size != 1:
            raise ValueError("strategy 'single' needs world_size 1")
        if self.parallelism.strategy == "ddp" and self.parallelism.world_size < 2:
            raise ValueError("strategy 'ddp' needs world_size of at least 2")
        if self.parallelism.strategy == "ddp" and self.parallelism.world_size != self.resources.gpu_count:
            raise ValueError("for 'ddp', world_size must equal resources.gpu_count")
        return self


StatusName = Literal["SCHEDULED", "RUNNING", "SUCCEEDED", "FAILED"]


class StatusReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StatusName
    reported_by: Literal["scheduler", "worker"]
    worker_id: str | None = Field(default=None, max_length=128)
    machine_type: str | None = Field(default=None, max_length=64)
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    reason: str | None = Field(default=None, max_length=1000)


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=128)
    sent_at: AwareDatetime
