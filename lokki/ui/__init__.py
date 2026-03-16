"""UI console module for lokki."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    """Entry point for lokki CLI."""
    parser = argparse.ArgumentParser(
        prog="lokki",
        description="Lokki - CLI for browsing flows, runs, and logs",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        help="AWS endpoint URL (e.g., http://localhost:4566 for LocalStack)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ui command - interactive TUI
    subparsers.add_parser("ui", help="Open interactive UI console")

    # list command - list flows
    list_parser = subparsers.add_parser("list", help="List all deployed flows")
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # runs command - list runs for a flow
    runs_parser = subparsers.add_parser("runs", help="List runs for a flow")
    runs_parser.add_argument(
        "flow",
        type=str,
        help="Flow name",
    )
    runs_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max number of runs (default: 10)",
    )
    runs_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # logs command - show logs for a run
    logs_parser = subparsers.add_parser("logs", help="Show logs for a run")
    logs_parser.add_argument(
        "flow",
        type=str,
        help="Flow name",
    )
    logs_parser.add_argument(
        "run_id",
        type=str,
        help="Run ID",
    )
    logs_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    try:
        if args.command == "ui":
            from lokki.ui.console import run_ui

            return run_ui(
                flow_name=None,
                region=args.region,
                endpoint=args.endpoint,
            )

        elif args.command == "list":
            from lokki.ui.api import list_flows

            flows = list_flows(
                region=args.region,
                endpoint=args.endpoint,
            )

            if args.json:
                import json

                print(json.dumps(flows, indent=2))
            else:
                if not flows:
                    print("No flows found")
                else:
                    for flow in flows:
                        print(flow)

            return 0

        elif args.command == "runs":
            from lokki.ui.api import list_runs

            runs = list_runs(
                flow_name=args.flow,
                region=args.region,
                endpoint=args.endpoint,
                max_count=args.limit,
            )

            if args.json:
                import json

                print(json.dumps(runs, indent=2))
            else:
                if not runs:
                    print(f"No runs found for flow '{args.flow}'")
                else:
                    print(f"Runs for {args.flow}:")
                    print(
                        f"{'Run ID':<20} {'Status':<12} {'Duration':<10} {'Start Time'}"
                    )
                    print("-" * 60)
                    for run in runs:
                        print(
                            f"{run.get('run_id', 'unknown'):<20} "
                            f"{run.get('status', 'UNKNOWN'):<12} "
                            f"{run.get('duration', '-'):<10} "
                            f"{run.get('start_time', '-')}"
                        )

            return 0

        elif args.command == "logs":
            from lokki.ui.api import get_logs

            logs = get_logs(
                flow_name=args.flow,
                run_id=args.run_id,
                region=args.region,
                endpoint=args.endpoint,
            )

            if args.json:
                import json

                print(json.dumps(logs, indent=2))
            else:
                if not logs:
                    print(f"No logs found for run '{args.run_id}'")
                else:
                    for log in logs:
                        print(log)

            return 0

        return 0

    except ImportError as e:
        print(f"Error: Required package not installed: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExiting...", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
