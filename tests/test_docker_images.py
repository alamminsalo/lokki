"""Integration tests for Lambda Docker images.

These tests build a Docker image with lokki to verify
Docker builds work correctly.
"""

import shutil
import subprocess
from pathlib import Path

import docker
import pytest

LOKKI_ROOT = Path(__file__).resolve().parent.parent
DOCKER_BUILD_FLOW = LOKKI_ROOT / "tests" / "flows" / "docker_build"


def get_docker_client():
    """Get Docker client."""
    try:
        return docker.from_env()
    except docker.errors.DockerException:
        pytest.skip("Docker not available")


DOCKERFILE_TEMPLATE = """FROM public.ecr.aws/lambda/python:3.13

COPY packages/ ${LAMBDA_TASK_ROOT}/

COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

ENV LAMBDA_TASK_ROOT=/var/task

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

    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            ".",
            "--no-installer-metadata",
            "--no-compile-bytecode",
            "--python",
            "3.13",
            "-t",
            str(packages_dir),
        ],
        cwd=str(DOCKER_BUILD_FLOW),
        capture_output=True,
    )

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

    # Cleanup: remove build artifacts to avoid pytest collecting them
    if build_dir.exists():
        shutil.rmtree(build_dir)

    try:
        client.images.remove(image_tag, force=True)
    except Exception:
        pass


class TestLambdaDockerImage:
    """Tests for Lambda Docker image using Docker SDK."""

    def test_docker_image_builds(self, docker_image):
        """Verify Docker image builds successfully."""
        result = subprocess.run(
            ["docker", "images", "-q", docker_image],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() != ""

    def test_docker_image_has_lokki(self, docker_image):
        """Verify lokki is installed in the Docker image."""
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                docker_image,
                "-c",
                "import lokki; print('OK')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "OK" in result.stdout
