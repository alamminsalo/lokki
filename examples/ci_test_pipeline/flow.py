"""Simple test pipeline for LocalStack deployment verification."""

import random

from lokki import flow, step


@step
def get_values(size: int) -> list[float]:
    return [random.random() - 0.5 for _ in range(size)]


@step
def transform(values: list[float], multiplier: float) -> list[float]:
    return [v * multiplier for v in values]


@flow
def ci_test_pipeline(
    size: int = 8,
    multiplier: int = 2,
):
    """
    CI test pipeline with 3 steps demonstrating:
    - Flow parameters (param1, multiplier)
    - Linear step chaining with .next()
    """
    return get_values(size).next(transform, multiplier=multiplier)


if __name__ == "__main__":
    from lokki import main

    main(ci_test_pipeline)
