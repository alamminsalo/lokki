"""Simple test pipeline for LocalStack deployment verification."""

from lokki import flow, step


@step
def get_values(param1: str) -> list:
    """First step - returns a list of values."""
    return [f"{param1}-a", f"{param1}-b", f"{param1}-c"]


@step
def process_item(item: str, multiplier: int) -> str:
    """Process each item in the map."""
    return f"{item}x{multiplier}"


@step
def transform_item(item: str) -> dict:
    """Transform item to dict."""
    return {"value": item, "processed": True}


@step
def combine_results(results: list, threshold: int) -> dict:
    """Aggregate results from the map."""
    valid = [r for r in results if r is not None]
    return {
        "count": len(valid),
        "items": valid,
        "threshold": threshold,
    }


@step
def print_result(result: dict):
    print(result)


@flow
def test_pipeline(
    param1: str = "test",
    multiplier: int = 2,
    threshold: int = 0,
):
    """
    Test pipeline with 5 steps demonstrating:
    - Flow parameters (param1, multiplier, threshold)
    - .map() with inner step
    - .agg() for aggregation
    """
    return (
        get_values(param1)
        .map(process_item, multiplier=multiplier)
        .next(transform_item)
        .agg(combine_results, threshold=threshold)
        .next(print_result)
    )


if __name__ == "__main__":
    from lokki import main

    main(test_pipeline)
