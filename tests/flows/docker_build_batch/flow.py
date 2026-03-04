"""Test flow with batch step for Docker build testing."""

from lokki import flow, step


@step(job_type="batch", vcpu=2, memory_mb=1024)
def heavy_computation(data: dict) -> dict:
    return {"result": data["value"] * 2}


@flow
def docker_build_batch():
    """Test flow with batch step for Docker build testing."""
    return heavy_computation()


if __name__ == "__main__":
    from lokki import main

    main(docker_build_batch)
