"""Integration tests for Lambda Docker images.

These tests build a Docker image with lokki to verify
Docker builds work correctly.
"""

import os
import shutil
import subprocess
from pathlib import Path

import docker
import pytest
import requests

LOKKI_ROOT = Path(__file__).resolve().parent.parent
DOCKER_BUILD_FLOW = LOKKI_ROOT / "tests" / "flows" / "docker_build"
DOCKER_BUILD_BATCH_FLOW = LOKKI_ROOT / "tests" / "flows" / "docker_build_batch"


def get_docker_client():
    """Get Docker client."""
    try:
        return docker.from_env()
    except Exception:
        pytest.skip("Docker not available")


DOCKERFILE_TEMPLATE = """FROM public.ecr.aws/lambda/python:3.13

RUN pip install pandas --no-cache-dir

COPY packages/ ${LAMBDA_TASK_ROOT}/

COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

ENV LAMBDA_TASK_ROOT=/var/task
ENV DOCKER_LAMBDA_STAY_OPEN=1

CMD ["handler.lambda_handler"]
"""


@pytest.fixture(scope="class")
def docker_image(tmp_path_factory):
    """Build Docker image with lokki from source."""
    client = get_docker_client()

    print("\n[docker_image] Building docker_build flow...")
    subprocess.run(
        ["uv", "run", "python", "flow.py", "build"],
        cwd=str(DOCKER_BUILD_FLOW),
        capture_output=True,
    )

    build_dir = DOCKER_BUILD_FLOW / "lokki-build"
    lambdas_dir = build_dir / "lambdas"
    if not lambdas_dir.exists():
        pytest.fail("Build did not create lambdas/ directory")

    print("\n[docker_image] Vendoring dependencies...")
    packages_dir = lambdas_dir / "packages"
    packages_dir.mkdir(exist_ok=True)
    print(f"[docker_image] packages_dir: {packages_dir}")

    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "../../../",
            "--target",
            str(packages_dir),
        ],
        cwd=str(DOCKER_BUILD_FLOW),
        capture_output=True,
        text=True,
    ).check_returncode()

    flow_source = DOCKER_BUILD_FLOW / "flow.py"
    flow_module_dir = packages_dir / "docker_build"
    flow_module_dir.mkdir(exist_ok=True)
    if flow_source.exists():
        shutil.copy(flow_source, flow_module_dir / "__init__.py")

    dockerfile = lambdas_dir / "Dockerfile"
    dockerfile.write_text(DOCKERFILE_TEMPLATE)

    image_tag = "lokki-test-docker:latest"

    try:
        print(f"\n[docker_image] Building Lambda image: {image_tag}")
        image, logs = client.images.build(
            path=str(lambdas_dir),
            tag=image_tag,
            rm=True,
        )
        print(f"[docker_image] Built: {image.id}")
    except Exception as e:
        pytest.fail(f"Docker build failed: {e}")

    yield image_tag


@pytest.fixture(scope="class")
def docker_container(docker_image):
    """Start a container with Lambda Runtime for HTTP testing."""
    client = get_docker_client()

    container = client.containers.run(
        docker_image,
        detach=True,
        ports={"8080/tcp": 8080},
        environment={
            "LOKKI_STEP_NAME": "get_data",
            "LOKKI_MODULE_NAME": "docker_build",
            "LOKKI_FLOW_NAME": "docker_build",
            "LOKKI_STORE_TYPE": "local",
        },
    )

    import time

    time.sleep(3)

    yield container

    container.stop(timeout=5)
    container.remove(force=True)


class TestLambdaDockerImage:
    """Tests for Lambda Docker image using Docker SDK."""

    def test_docker_image_builds(self, docker_image):
        """Verify Docker image builds successfully."""
        subprocess.run(
            ["docker", "images", "-q", docker_image],
            capture_output=True,
            text=True,
        ).check_returncode()

    def test_lambda_handler_invocation(self, docker_container):
        """Test Lambda handler can be invoked via HTTP POST."""
        event = {
            "input": None,
            "flow": {
                "run_id": "test-run-123",
                "params": {},
            },
        }

        url = "http://localhost:8080/2015-03-31/functions/function/invocations"
        response = requests.post(url, json=event, timeout=30)

        assert response.status_code == 200, f"Failed: {response.text}"

        result = response.json()
        assert "input" in result
        assert "flow" in result
        assert result["input"] is not None
        assert result["flow"]["run_id"] == "test-run-123"


@pytest.fixture(scope="class")
def batch_build_files(tmp_path_factory):
    """Build batch flow and return build directory."""
    print("\n[batch_build_files] Building docker_build_batch flow...")
    subprocess.run(
        ["uv", "run", "python", "flow.py", "build"],
        cwd=str(DOCKER_BUILD_BATCH_FLOW),
        capture_output=True,
    )

    build_dir = DOCKER_BUILD_BATCH_FLOW / "lokki-build"

    if not (build_dir / "batch.py").exists():
        pytest.fail("Build did not create batch.py")

    if not (build_dir / "batch_main.py").exists():
        pytest.fail("Build did not create batch_main.py")

    if not (build_dir / "pyproject.toml").exists():
        pytest.fail("Build did not create pyproject.toml")

    if not (build_dir / "uv.lock").exists():
        pytest.fail("Build did not create uv.lock")

    yield build_dir


class TestBatchDockerFiles:
    """Tests for Batch Docker file generation."""

    def test_batch_dockerfile_exists(self, batch_build_files):
        """Verify batch Dockerfile exists."""
        assert (batch_build_files / "Dockerfile").exists()

    def test_batch_dockerfile_contains_batch_main(self, batch_build_files):
        """Verify batch Dockerfile contains batch_main.py reference."""
        dockerfile_content = (batch_build_files / "Dockerfile").read_text()
        assert "batch_main.py" in dockerfile_content
        assert "lokki.runtime.batch_main" in dockerfile_content

    def test_batch_directory_has_required_files(self, batch_build_files):
        """Verify batch directory has all required files."""
        assert (batch_build_files / "Dockerfile").exists()
        assert (batch_build_files / "batch.py").exists()
        assert (batch_build_files / "batch_main.py").exists()
        assert (batch_build_files / "pyproject.toml").exists()
        assert (batch_build_files / "uv.lock").exists()

    def test_batch_handler_template(self, batch_build_files):
        """Verify batch handler uses importlib for dynamic imports."""
        batch_handler = (batch_build_files / "batch.py").read_text()
        assert "import importlib" in batch_handler
        assert "LOKKI_STEP_NAME" in batch_handler
        assert "make_batch_handler" in batch_handler

    def test_batch_main_can_execute_with_env(self, batch_build_files):
        """Verify batch_main can execute with proper environment variables."""
        import json
        import subprocess
        import sys

        flow_module_dir = batch_build_files / "docker_build_batch"
        flow_module_dir.mkdir(exist_ok=True)
        flow_source = DOCKER_BUILD_BATCH_FLOW / "flow.py"
        if flow_source.exists():
            shutil.copy(flow_source, flow_module_dir / "__init__.py")

        input_event = {
            "input": {"value": 5},
            "flow": {"run_id": "test-run-123", "params": {}},
        }

        env = {
            **os.environ,
            "LOKKI_STEP_NAME": "heavy_computation",
            "LOKKI_MODULE_NAME": "docker_build_batch",
            "LOKKI_INPUT_DATA": json.dumps(input_event),
            "LOKKI_FLOW_NAME": "docker_build_batch",
            "LOKKI_RUN_ID": "test-run-123",
            "LOKKI_STORE_TYPE": "local",
        }

        result = subprocess.run(
            [sys.executable, "-m", "lokki.runtime.batch_main"],
            cwd=str(batch_build_files),
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_batch_main_validates_step_name(self, batch_build_files):
        """Verify batch_main validates LOKKI_STEP_NAME environment variable."""
        import subprocess
        import sys

        flow_module_dir = batch_build_files / "docker_build_batch"
        flow_module_dir.mkdir(exist_ok=True)

        env = {
            **os.environ,
            "LOKKI_STEP_NAME": "",
            "LOKKI_MODULE_NAME": "docker_build_batch",
        }

        result = subprocess.run(
            [sys.executable, "-m", "lokki.runtime.batch_main"],
            cwd=str(batch_build_files),
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode != 0
        assert "LOKKI_STEP_NAME" in result.stderr
