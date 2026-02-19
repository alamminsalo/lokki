"""Lokki - Python library for data pipelines on AWS Step Functions."""

import sys
from collections.abc import Callable

from lokki.decorators import flow, step
from lokki.graph import FlowGraph

__all__ = ["flow", "step", "main"]


def main(flow_fn: Callable[[], FlowGraph]) -> None:
    """CLI entry point for lokki flows.

    Usage:
        python flow_script.py build  # Build deployment artifacts
        python flow_script.py run    # Run locally
    """
    if len(sys.argv) < 2 or sys.argv[1] == "--help" or sys.argv[1] == "-h":
        print("Usage: python <flow_script.py> <command>")
        print()
        print("Commands:")
        print("  build  Build deployment artifacts")
        print("         (Lambda Docker images, Step Functions state machine,")
        print("         CloudFormation template)")
        print("  run    Run the flow locally using temporary local storage")
        print()
        print("Examples:")
        print("  python my_flow.py run")
        print("  python my_flow.py build")
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: python <flow_script.py> <command>")
        print("Run 'python <flow_script.py> --help' for more information.")
        sys.exit(1)

    command = sys.argv[1]

    if command == "build":
        from lokki.builder.builder import Builder
        from lokki.config import load_config

        try:
            graph = flow_fn()
        except Exception as e:
            print(f"Error: Failed to create flow graph: {e}")
            sys.exit(1)

        try:
            config = load_config()
        except Exception as e:
            print(f"Error: Failed to load configuration: {e}")
            sys.exit(1)

        if not config.artifact_bucket:
            print("Error: 'artifact_bucket' is not configured.")
            print("Please set it in lokki.yml or via LOKKI_ARTIFACT_BUCKET env var.")
            sys.exit(1)

        if not config.ecr_repo_prefix:
            print("Error: 'ecr_repo_prefix' is not configured.")
            print("Please set it in lokki.yml or via LOKKI_ECR_REPO_PREFIX env var.")
            sys.exit(1)

        Builder.build(graph, config)
        print("Build complete!")
    elif command == "run":
        from lokki.runner import LocalRunner

        try:
            graph = flow_fn()
        except Exception as e:
            print(f"Error: Failed to create flow graph: {e}")
            sys.exit(1)

        runner = LocalRunner()
        try:
            result = runner.run(graph)
            print(result)
        except Exception as e:
            print(f"Error: Failed to run flow: {e}")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        print("Usage: python <flow_script.py> <build|run>")
        sys.exit(1)
