"""Test pipeline for map without aggregation - event sending pattern."""

from lokki import flow, step


SENT_EVENTS: list[dict] = []


@step
def get_events() -> list[dict]:
    """Generate a list of events to send."""
    return [
        {"id": 1, "type": "user.created", "payload": {"name": "Alice"}},
        {"id": 2, "type": "user.created", "payload": {"name": "Bob"}},
        {"id": 3, "type": "user.created", "payload": {"name": "Charlie"}},
    ]


@step
def send_webhook(event: dict) -> dict:
    """Send webhook for each event - side effect only."""
    # In real usage, this would send an HTTP request
    SENT_EVENTS.append(event)
    return {"status": "sent", "event_id": event["id"]}


@flow
def map_only_flow():
    """
    Flow that maps over events without aggregation.
    Each event is processed independently - useful for:
    - Sending webhooks
    - Sending notifications
    - Data export pipelines
    """
    return get_events().map(send_webhook)


if __name__ == "__main__":
    from lokki import main

    main(map_only_flow)
