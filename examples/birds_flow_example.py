"""Birds flow example for lokki."""

from lokki import flow, step


@step
def get_birds() -> list[str]:
    return ["goose", "duck", "seagul"]


@step
def uppercase_list(birds: list[str]) -> list[str]:
    return [b.upper() for b in birds]


@step
def lowercase(bird: str) -> str:
    return bird.lower()


@step
def flap_bird(bird: str) -> str:
    return f"flappy {bird}"


@step
def join_birds(birds: list[str]) -> str:
    return ", ".join(birds)


@flow
def birds_flow():
    return (
        get_birds().next(uppercase_list).map(flap_bird).next(lowercase).agg(join_birds)
    )


if __name__ == "__main__":
    from lokki import main

    main(birds_flow)
