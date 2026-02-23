"""Entry point for AWS Batch jobs."""

import json
import os


def main() -> None:
    """Main entry point for AWS Batch container."""
    input_data = os.environ.get("LOKKI_INPUT_DATA", "")
    step_name = os.environ.get("LOKKI_STEP_NAME", "")
    module_name = os.environ.get("LOKKI_MODULE_NAME", "")

    if not step_name:
        raise ValueError("LOKKI_STEP_NAME environment variable not set")

    if not module_name:
        raise ValueError("LOKKI_MODULE_NAME environment variable not set")

    import importlib

    mod = importlib.import_module(module_name)

    step_node = getattr(mod, step_name, None)
    if step_node is None:
        raise ValueError(
            f"Step function '{step_name}' not found in module '{module_name}'"
        )

    step_func = step_node.fn if hasattr(step_node, "fn") else step_node

    from lokki.runtime.batch import make_batch_handler

    handler = make_batch_handler(step_func)

    event = {}
    if input_data:
        try:
            event = json.loads(input_data)
        except json.JSONDecodeError:
            event = {"input_data": input_data}

    result = handler(event)

    output = json.dumps(result)
    print(output)


if __name__ == "__main__":
    main()
