"""Test flow with both Lambda and Batch steps for state machine testing."""

from lokki import flow, step


@step
def fetch_data() -> dict:
    return {"values": [1, 2, 3, 4, 5]}


@step(job_type="batch", vcpu=2, memory_mb=1024)
def process_batch(data: dict) -> dict:
    return {"processed": sum(data.get("values", []))}


@step
def format_output(result: dict) -> str:
    return f"Final result: {result.get('processed', 0)}"


@flow
def lambda_batch_pipeline():
    """Test flow with both Lambda and Batch steps for state machine testing."""
    return fetch_data().next(process_batch).next(format_output)


if __name__ == "__main__":
    from lokki import main

    main(lambda_batch_pipeline)
