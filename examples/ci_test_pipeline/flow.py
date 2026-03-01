"""Simple test pipeline for LocalStack deployment verification."""

import random

from lokki import flow, step


@step
def get_values(size: int) -> list[float]:
    return [random.random() - 0.5 for _ in range(size)]


@step
def transform(values: list[float]) -> list[float]:
    return values  # Flow params automatically filtered if not accepted


@flow
def ci_test_pipeline(
    size: int = 8,
    multiplier: int = 2,
):
    """
    CI test pipeline with 3 steps demonstrating:
    - Flow parameters (size, multiplier)
    - Linear step chaining with .next()
    """
    return get_values(size).next(transform)


if __name__ == "__main__":
    from lokki import main

    main(ci_test_pipeline)
