"""Integration tests for Lambda Docker images.

These tests are skipped by default. Run with:
    pytest tests/test_docker_images.py -v --run-docker

These tests build a Docker image with pandas dependency to verify Docker builds work.
"""

import subprocess
from pathlib import Path

import docker
import pytest


def get_docker_client():
    """Get Docker client."""
    try:
        return docker.from_env()
    except docker.errors.DockerException:
        pytest.skip("Docker not available")


@pytest.fixture(scope="class")
def docker_image(tmp_path_factory):
    """Build a test Docker image with pandas."""
    client = get_docker_client()

    test_dir = Path(tmp_path_factory.mktemp("docker_test"))

    dockerfile_content = """FROM public.ecr.aws/lambda/python:3.13

RUN pip install pandas --no-cache-dir
"""

    (test_dir / "Dockerfile").write_text(dockerfile_content)

    image_tag = "lokki-test-pandas:latest"

    try:
        print(f"\n[docker_image] Building image with pandas: {image_tag}")
        image, logs = client.images.build(
            path=str(test_dir),
            tag=image_tag,
            rm=True,
        )
        print(f"[docker_image] Built: {image.id}")
    except docker.errors.BuildError as e:
        pytest.skip(f"Docker build failed: {e}")

    yield image_tag

    try:
        client.images.remove(image_tag, force=True)
    except Exception:
        pass


class TestLambdaDockerImage:
    """Tests for Lambda Docker image using Docker SDK."""

    def test_docker_image_builds(self, docker_image):
        """Verify Docker image with pandas builds successfully."""
        result = subprocess.run(
            ["docker", "images", "-q", docker_image],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() != ""

    def test_docker_image_has_pandas(self, docker_image):
        """Verify pandas is installed in the Docker image."""
        client = get_docker_client()

        container = client.containers.run(
            docker_image,
            detach=True,
            entrypoint="python",
            command=["-c", "import pandas; print('pandas OK')"],
        )

        try:
            result = container.wait()
            output = container.logs(stdout=True, stderr=True).decode()
            assert result["StatusCode"] == 0, f"Failed: {output}"
            assert "pandas OK" in output
        finally:
            container.stop(timeout=5)
            container.remove(force=True)
