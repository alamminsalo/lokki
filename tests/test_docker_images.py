"""Integration tests for Lambda Docker images.

These tests build a Docker image with lokki to verify
Docker builds work correctly.
"""

import shutil
import subprocess
from pathlib import Path

import docker
import pytest
import requests

LOKKI_ROOT = Path(__file__).resolve().parent.parent
DOCKER_BUILD_FLOW = LOKKI_ROOT / "tests" / "flows" / "docker_build"


def get_docker_client():
    """Get Docker client."""
    try:
        return docker.from_env()
    except docker.errors.DockerException:
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

    # Vendor all dependencies using uv
    print("\n[docker_image] Vendoring dependencies...")
    packages_dir = lambdas_dir / "packages"
    packages_dir.mkdir(exist_ok=True)
    print(f"[docker_image] packages_dir: {packages_dir}")

    # Install to packages directory with manylinux2014 platform
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

    # Copy flow module source so handler can import it
    flow_source = DOCKER_BUILD_FLOW / "flow.py"
    flow_module_dir = packages_dir / "docker_build"
    flow_module_dir.mkdir(exist_ok=True)
    if flow_source.exists():
        shutil.copy(flow_source, flow_module_dir / "__init__.py")

    # Write static Dockerfile that uses packages directory
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
    except docker.errors.BuildError as e:
        pytest.fail(f"Docker build failed: {e}")

    yield image_tag


@pytest.fixture(scope="class")
def docker_container(docker_image):
    """Start a container with Lambda Runtime for HTTP testing."""
    client = get_docker_client()

    # Run container with Lambda Runtime API
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

    # Wait for Lambda Runtime to start
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
        # Local store returns file path, verify it's a valid path
        assert result["input"] is not None
        assert result["flow"]["run_id"] == "test-run-123"
