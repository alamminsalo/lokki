"""Lokki - Python library for data pipelines on AWS Step Functions."""

import argparse
import inspect
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args, get_origin

from lokki.decorators import flow, step
from lokki.graph import FlowGraph

__all__ = ["flow", "step", "main"]


def _get_flow_params(
    flow_fn: Callable[..., FlowGraph],
) -> dict[str, inspect.Parameter]:
    """Get the parameters of the flow function."""
    fn = getattr(flow_fn, "_fn", flow_fn)
    sig = inspect.signature(fn)
    return dict(sig.parameters)


def _coerce_value(value: str, param_type: type) -> Any:
    """Coerce a string value to the expected type."""
    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin is list and args:
        list_type = args[0]
        return [list_type(item.strip()) for item in value.split(",")]

    if param_type is bool:
        lower = value.lower()
        if lower in ("true", "1", "yes"):
            return True
        if lower in ("false", "0", "no"):
            return False
        raise ValueError(f"Invalid boolean value: {value}")

    if param_type is int:
        try:
            return int(value)
        except ValueError as e:
            raise ValueError(f"Invalid integer value: {value}") from e

    if param_type is float:
        try:
            return float(value)
        except ValueError as e:
            raise ValueError(f"Invalid float value: {value}") from e

    return param_type(value)


def _parse_flow_params(
    flow_fn: Callable[..., FlowGraph], args: argparse.Namespace
) -> dict[str, Any]:
    """Parse and validate flow function parameters from parsed args."""
    params = _get_flow_params(flow_fn)
    result: dict[str, Any] = {}

    for name, param in params.items():
        value = getattr(args, name, None)
        if value is not None:
            try:
                result[name] = _coerce_value(value, param.annotation)
            except (ValueError, TypeError) as e:
                msg = f"Invalid value for '--{name}': {e}"
                raise argparse.ArgumentTypeError(msg) from e

    missing = [
        f"--{name}"
        for name, param in params.items()
        if param.default is inspect.Parameter.empty and name not in result
    ]
    if missing:
        missing_str = ", ".join(missing)
        raise argparse.ArgumentError(
            None, f"Missing required parameter(s): {missing_str}"
        )

    return result


def main(flow_fn: Callable[..., FlowGraph]) -> None:
    """CLI entry point for lokki flows.

    Usage:
        python flow_script.py build              # Build deployment artifacts
        python flow_script.py run                # Run locally
        python flow_script.py run --start-date 2024-01-15  # Run with params
        python flow_script.py deploy             # Build and deploy to AWS
    """
    params = _get_flow_params(flow_fn)

    parser = argparse.ArgumentParser(
        prog="flow_script.py",
        description="Lokki - Python library for data pipelines on AWS Step Functions",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the flow locally")
    for name, param in params.items():
        has_default = param.default is not inspect.Parameter.empty
        cli_name = name.replace("_", "-")
        if has_default:
            run_parser.add_argument(
                f"--{cli_name}",
                dest=name,
                type=str,
                default=None,
                help=f"(default: {param.default})",
            )
        else:
            run_parser.add_argument(
                f"--{cli_name}",
                dest=name,
                type=str,
                required=True,
                help="(required)",
            )

    subparsers.add_parser(
        "build",
        help="Build deployment artifacts (Lambda, Step Functions, CloudFormation)",
    )

    deploy_parser = subparsers.add_parser("deploy", help="Build and deploy to AWS")
    deploy_parser.add_argument(
        "--stack-name", default=None, help="CloudFormation stack name"
    )
    deploy_parser.add_argument(
        "--region", default=None, help="AWS region (default: from AWS config)"
    )
    deploy_parser.add_argument(
        "--image-tag", default="latest", help="Docker image tag (default: latest)"
    )
    deploy_parser.add_argument(
        "--confirm", action="store_true", help="Skip confirmation prompt"
    )

    subparsers.add_parser(
        "destroy", help="Destroy the CloudFormation stack (not implemented)"
    )
    subparsers.add_parser(
        "status", help="Show flow run status on AWS (not implemented)"
    )
    subparsers.add_parser("logs", help="Fetch logs from AWS (not implemented)")

    args = parser.parse_args()
    command = args.command

    if command == "run":
        from lokki.config import load_config
        from lokki.runner import LocalRunner

        try:
            flow_params = _parse_flow_params(flow_fn, args)
        except (argparse.ArgumentError, argparse.ArgumentTypeError) as e:
            print(f"Error: {e}")
            sys.exit(1)

        try:
            graph = flow_fn(**flow_params)
        except Exception as e:
            print(f"Error: Failed to create flow graph: {e}")
            sys.exit(1)

        try:
            config = load_config()
        except Exception:
            config = None

        runner = LocalRunner(logging_config=config.logging if config else None)
        try:
            result = runner.run(graph, flow_params)
            print(result)
        except Exception as e:
            print(f"Error: Failed to run flow: {e}")
            sys.exit(1)

    elif command == "build":
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
            print("Please set it in lokki.toml or via LOKKI_ARTIFACT_BUCKET env var.")
            sys.exit(1)

        Builder.build(graph, config, flow_fn)
        print("Build complete!")

    elif command == "deploy":
        from lokki.builder.builder import Builder
        from lokki.config import load_config
        from lokki.deploy import Deployer, DeployError, DockerNotAvailableError

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
            print("Please set it in lokki.toml or via LOKKI_ARTIFACT_BUCKET env var.")
            sys.exit(1)

        stack_name = args.stack_name or f"{graph.name}-stack"

        print(f"Deploying flow '{graph.name}' to stack '{stack_name}'...")
        print()

        try:
            Builder.build(graph, config, flow_fn)
            print()
        except Exception as e:
            print(f"Error: Build failed: {e}")
            sys.exit(1)

        try:
            deployer = Deployer(
                stack_name=stack_name,
                region=args.region or "us-east-1",
                image_tag=args.image_tag,
                endpoint=config.aws_endpoint,
                package_type=config.lambda_cfg.package_type,
            )
            deployer.deploy(
                flow_name=graph.name,
                artifact_bucket=config.artifact_bucket,
                image_repository=config.image_repository,
                build_dir=Path(config.build_dir),
                aws_endpoint=config.aws_endpoint,
                package_type=config.lambda_cfg.package_type,
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

    elif command == "destroy":
        print("Error: 'destroy' command is not implemented yet.")
        sys.exit(1)

    elif command == "status":
        print("Error: 'status' command is not implemented yet.")
        sys.exit(1)

    elif command == "logs":
        print("Error: 'logs' command is not implemented yet.")
        sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)
