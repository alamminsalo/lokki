"""Tests for AWS Batch integration."""

import pytest

from lokki import flow, step
from lokki.config import BatchConfig, LokkiConfig
from lokki.decorators import JobTypeConfig
from lokki.graph import TaskEntry


class TestBatchConfig:
    def test_batch_config_defaults(self):
        config = BatchConfig()
        assert config.job_queue == ""
        assert config.job_definition_name == ""
        assert config.timeout_seconds == 3600
        assert config.vcpu == 2
        assert config.memory_mb == 4096
        assert config.image == ""

    def test_batch_config_custom_values(self):
        config = BatchConfig(
            job_queue="my-queue",
            job_definition_name="my-job-def",
            timeout_seconds=7200,
            vcpu=4,
            memory_mb=16384,
            image="my-image:latest",
        )
        assert config.job_queue == "my-queue"
        assert config.job_definition_name == "my-job-def"
        assert config.timeout_seconds == 7200
        assert config.vcpu == 4
        assert config.memory_mb == 16384
        assert config.image == "my-image:latest"


class TestJobTypeConfig:
    def test_job_type_defaults(self):
        config = JobTypeConfig()
        assert config.job_type == "lambda"
        assert config.vcpu is None
        assert config.memory_mb is None
        assert config.timeout_seconds is None

    def test_job_type_batch(self):
        config = JobTypeConfig(job_type="batch", vcpu=8, memory_mb=16384)
        assert config.job_type == "batch"
        assert config.vcpu == 8
        assert config.memory_mb == 16384

    def test_invalid_job_type(self):
        with pytest.raises(ValueError, match="job_type must be 'lambda' or 'batch'"):
            JobTypeConfig(job_type="invalid")

    def test_invalid_vcpu(self):
        with pytest.raises(ValueError, match="vcpu must be positive"):
            JobTypeConfig(vcpu=0)


class TestStepDecoratorWithBatch:
    def test_step_with_job_type_batch(self):
        @step(job_type="batch")
        def my_step(data):
            return data

        assert my_step.job_type == "batch"
        assert my_step.vcpu is None
        assert my_step.memory_mb is None
        assert my_step.timeout_seconds is None

    def test_step_with_batch_params(self):
        @step(job_type="batch", vcpu=8, memory_mb=16384, timeout_seconds=7200)
        def my_step(data):
            return data

        assert my_step.job_type == "batch"
        assert my_step.vcpu == 8
        assert my_step.memory_mb == 16384
        assert my_step.timeout_seconds == 7200

    def test_step_lambda_is_default(self):
        @step
        def my_step(data):
            return data

        assert my_step.job_type == "lambda"

    def test_step_explicit_lambda(self):
        @step(job_type="lambda")
        def my_step(data):
            return data

        assert my_step.job_type == "lambda"
        assert my_step.vcpu is None
        assert my_step.memory_mb is None


class TestFlowGraphWithBatch:
    def test_single_batch_step(self):
        @step(job_type="batch", vcpu=4, memory_mb=8192)
        def process(data):
            return data

        @flow
        def my_flow():
            return process()

        graph = my_flow()
        assert len(graph.entries) == 1
        entry = graph.entries[0]
        assert isinstance(entry, TaskEntry)
        assert entry.job_type == "batch"
        assert entry.vcpu == 4
        assert entry.memory_mb == 8192

    def test_mixed_lambda_and_batch(self):
        @step
        def get_data():
            return [1, 2, 3]

        @step(job_type="batch", vcpu=8)
        def process_batch(item):
            return item * 2

        @step
        def save_results(result):
            return result

        @flow
        def mixed_flow():
            return get_data().map(process_batch).agg(save_results)

        graph = mixed_flow()

        from lokki.graph import MapOpenEntry

        map_entries = [e for e in graph.entries if isinstance(e, MapOpenEntry)]
        assert len(map_entries) == 1

        inner_steps = map_entries[0].inner_steps
        batch_steps = [
            s for s in inner_steps if getattr(s, "job_type", "lambda") == "batch"
        ]
        assert len(batch_steps) == 1
        assert batch_steps[0].name == "process_batch"
        assert batch_steps[0].vcpu == 8


class TestBatchConfigInLokkiConfig:
    def test_lokki_config_with_batch(self):
        config = LokkiConfig.from_dict(
            {
                "batch": {
                    "job_queue": "test-queue",
                    "job_definition_name": "test-job",
                    "timeout_seconds": 1800,
                    "vcpu": 4,
                    "memory_mb": 8192,
                    "image": "test-image:latest",
                }
            }
        )

        assert config.batch_cfg.job_queue == "test-queue"
        assert config.batch_cfg.job_definition_name == "test-job"
        assert config.batch_cfg.timeout_seconds == 1800
        assert config.batch_cfg.vcpu == 4
        assert config.batch_cfg.memory_mb == 8192
        assert config.batch_cfg.image == "test-image:latest"

    def test_lokki_config_batch_defaults(self):
        config = LokkiConfig.from_dict({})

        assert config.batch_cfg.job_queue == ""
        assert config.batch_cfg.job_definition_name == ""
        assert config.batch_cfg.vcpu == 2
        assert config.batch_cfg.memory_mb == 4096
