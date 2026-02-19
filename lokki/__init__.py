"""Lokki - Python library for data pipelines on AWS Step Functions."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from lokki.decorators import flow, step
from lokki.graph import FlowGraph

__all__ = ["flow", "step", "main"]


def main(flow_fn: Callable[[], FlowGraph]) -> None:
    """CLI entry point for lokki flows.

    Usage:
        python flow_script.py build  # Build deployment artifacts
        python flow_script.py run    # Run locally
        python flow_script.py deploy # Build and deploy to AWS
    """
    if len(sys.argv) < 2 or sys.argv[1] == "--help" or sys.argv[1] == "-h":
        print("Usage: python <flow_script.py> <command>")
        print()
        print("Commands:")
        print("  build   Build deployment artifacts")
        print("          (Lambda Docker images, Step Functions state machine,")
        print("          CloudFormation template)")
        print("  run     Run the flow locally using temporary local storage")
        print("  deploy  Build and deploy to AWS Step Functions")
        print()
        print("Deploy Options:")
        print("  --stack-name NAME   CloudFormation stack name")
        print("  --region REGION    AWS region (default: from AWS config)")
        print("  --image-tag TAG    Docker image tag (default: latest)")
        print("  --confirm          Skip confirmation prompt")
        print()
        print("Examples:")
        print("  python my_flow.py run")
        print("  python my_flow.py build")
        print("  python my_flow.py deploy --region eu-west-1")
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

        if not config.aws.artifact_bucket:
            print("Error: 'aws.artifact_bucket' is not configured.")
            print("Please set it in lokki.yml or via LOKKI_ARTIFACT_BUCKET env var.")
            sys.exit(1)

        if not config.aws.ecr_repo_prefix:
            print("Error: 'aws.ecr_repo_prefix' is not configured.")
            print("Please set it in lokki.yml or via LOKKI_ECR_REPO_PREFIX env var.")
            sys.exit(1)

        Builder.build(graph, config)
        print("Build complete!")
    elif command == "run":
        from lokki.config import load_config
        from lokki.runner import LocalRunner

        try:
            graph = flow_fn()
        except Exception as e:
            print(f"Error: Failed to create flow graph: {e}")
            sys.exit(1)

        try:
            config = load_config()
        except Exception:
            config = None

        runner = LocalRunner(logging_config=config.logging if config else None)
        try:
            result = runner.run(graph)
            print(result)
        except Exception as e:
            print(f"Error: Failed to run flow: {e}")
            sys.exit(1)
    elif command == "deploy":
        from lokki.builder.builder import Builder
        from lokki.config import load_config
        from lokki.deploy import Deployer, DeployError, DockerNotAvailableError

        parser = argparse.ArgumentParser(prog="deploy")
        parser.add_argument("--stack-name", default=None)
        parser.add_argument("--region", default=None)
        parser.add_argument("--image-tag", default="latest")
        parser.add_argument("--confirm", action="store_true")
        args, _ = parser.parse_known_args(sys.argv[2:])

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

        if not config.aws.artifact_bucket:
            print("Error: 'aws.artifact_bucket' is not configured.")
            print("Please set it in lokki.yml or via LOKKI_ARTIFACT_BUCKET env var.")
            sys.exit(1)

        if not config.aws.ecr_repo_prefix:
            print("Error: 'aws.ecr_repo_prefix' is not configured.")
            print("Please set it in lokki.yml or via LOKKI_ECR_REPO_PREFIX env var.")
            sys.exit(1)

        stack_name = args.stack_name or f"{graph.name}-stack"

        print(f"Deploying flow '{graph.name}' to stack '{stack_name}'...")
        print()

        try:
            Builder.build(graph, config)
            print()
        except Exception as e:
            print(f"Error: Build failed: {e}")
            sys.exit(1)

        try:
            deployer = Deployer(
                stack_name=stack_name,
                region=args.region or "us-east-1",
                image_tag=args.image_tag,
            )
            deployer.deploy(
                flow_name=graph.name,
                artifact_bucket=config.aws.artifact_bucket,
                ecr_repo_prefix=config.aws.ecr_repo_prefix,
                build_dir=Path(config.build_dir),
            )
            print()
            print("Deploy complete!")
        except DockerNotAvailableError as e:
            print(f"Error: {e}")
            print("You can run 'build' first, then manually push images and deploy.")
            sys.exit(1)
        except DeployError as e:
            print(f"Error: Deploy failed: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error: Unexpected error: {e}")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        print("Usage: python <flow_script.py> <build|run|deploy>")
        sys.exit(1)
