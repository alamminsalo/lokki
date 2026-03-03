"""Simple test flow with pandas dependency for Docker build testing."""

import pandas as pd

from lokki import flow, step


@step
def get_data() -> dict:
    return {"values": [1, 2, 3, 4, 5]}


@step
def process_data(data: dict) -> dict:
    df = pd.DataFrame(data)
    return {"sum": int(df["values"].sum()), "count": len(data["values"])}


@flow
def docker_build():
    """Test flow with pandas dependency for Docker build testing."""
    return get_data().next(process_data)


if __name__ == "__main__":
    from lokki import main

    main(docker_build)
