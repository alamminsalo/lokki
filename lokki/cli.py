"""CLI module for lokki - extracted from __init__.py."""

import argparse
import inspect
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args, get_origin

from lokki._errors import DeployError, DockerNotAvailableError
from lokki.graph import FlowGraph


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


def _get_step_names(graph: FlowGraph) -> list[str]:
    """Get all step names from a flow graph."""
    from lokki._utils import get_step_names

    return list(get_step_names(graph))


def _handle_run(args: argparse.Namespace, flow_fn: Callable[..., FlowGraph]) -> None:
    """Handle the 'run' command."""
    from lokki.config import load_config
    from lokki.runtime.local import LocalRunner

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


def _handle_build(args: argparse.Namespace, flow_fn: Callable[..., FlowGraph]) -> None:
    """Handle the 'build' command."""
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


def _handle_deploy(args: argparse.Namespace, flow_fn: Callable[..., FlowGraph]) -> None:
    """Handle the 'deploy' command."""
    from lokki.builder.builder import Builder
    from lokki.config import load_config
    from lokki.deploy import Deployer

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
        Builder.build(graph, config, flow_fn, force=args.force)
        print()
    except Exception as e:
        print(f"Error: Build failed: {e}")
        sys.exit(1)

    try:
        deployer = Deployer(
            stack_name=stack_name,
            region=args.region or config.aws_region,
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


def _handle_show(args: argparse.Namespace, flow_fn: Callable[..., FlowGraph]) -> None:
    """Handle the 'show' command."""
    from lokki.config import load_config
    from lokki.show import show

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

    region = config.aws_region
    endpoint = config.aws_endpoint

    show(
        flow_name=graph.name,
        max_count=args.n,
        run_id=args.run,
        region=region,
        endpoint=endpoint,
    )


def _handle_logs(args: argparse.Namespace, flow_fn: Callable[..., FlowGraph]) -> None:
    """Handle the 'logs' command."""
    from lokki.config import load_config
    from lokki.logs import logs

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

    step_names = _get_step_names(graph)
    region = config.aws_region
    endpoint = config.aws_endpoint

    logs(
        flow_name=graph.name,
        step_names=step_names,
        start_time=args.start,
        end_time=args.end,
        run_id=args.run,
        region=region,
        endpoint=endpoint,
        tail=args.tail,
    )


def _handle_destroy(
    args: argparse.Namespace, flow_fn: Callable[..., FlowGraph]
) -> None:
    """Handle the 'destroy' command."""
    from lokki.config import load_config
    from lokki.destroy import destroy

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

    stack_name = f"{graph.name}-stack"
    region = config.aws_region
    endpoint = config.aws_endpoint

    destroy(
        stack_name=stack_name,
        region=region,
        endpoint=endpoint,
        confirm=args.confirm,
    )


def main(flow_fn: Callable[..., FlowGraph]) -> None:
    """CLI entry point for lokki flows."""
    params = _get_flow_params(flow_fn)

    parser = argparse.ArgumentParser(
        prog="flow_script.py",
        description="Lokki - Python library for data pipelines on AWS Step Functions",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run parser
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

    # build parser
    subparsers.add_parser(
        "build",
        help="Build deployment artifacts (Lambda, Step Functions, CloudFormation)",
    )

    # deploy parser
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
    deploy_parser.add_argument(
        "--force", action="store_true", help="Force rebuild even if build dir exists"
    )

    # show parser
    show_parser = subparsers.add_parser("show", help="Show flow run status on AWS")
    show_parser.add_argument(
        "--n", type=int, default=10, help="Number of runs to show (default: 10)"
    )
    show_parser.add_argument("--run", type=str, help="Specific run ID to show")

    # logs parser
    logs_parser = subparsers.add_parser("logs", help="Fetch CloudWatch logs")
    logs_parser.add_argument(
        "--start",
        type=str,
        help="Start time (ISO 8601 format, e.g., 2024-01-15T10:00:00Z)",
    )
    logs_parser.add_argument(
        "--end", type=str, help="End time (ISO 8601 format, e.g., 2024-01-15T12:00:00Z)"
    )
    logs_parser.add_argument("--run", type=str, help="Specific run ID to filter logs")
    logs_parser.add_argument(
        "--tail", action="store_true", help="Tail logs in real-time"
    )

    # destroy parser
    destroy_parser = subparsers.add_parser(
        "destroy", help="Destroy the CloudFormation stack"
    )
    destroy_parser.add_argument(
        "--confirm", action="store_true", help="Skip confirmation prompt"
    )

    args = parser.parse_args()
    command = args.command

    if command == "run":
        _handle_run(args, flow_fn)
    elif command == "build":
        _handle_build(args, flow_fn)
    elif command == "deploy":
        _handle_deploy(args, flow_fn)
    elif command == "show":
        _handle_show(args, flow_fn)
    elif command == "logs":
        _handle_logs(args, flow_fn)
    elif command == "destroy":
        _handle_destroy(args, flow_fn)
    else:
        parser.print_help()
        sys.exit(1)
