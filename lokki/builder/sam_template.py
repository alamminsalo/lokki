"""SAM template generation for local testing with sam local."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def build_sam_template(graph: FlowGraph, config: LokkiConfig, build_dir: Path) -> str:
    """Build a SAM template for local testing with sam local."""
    resources: dict[str, dict[str, Any]] = {}

    step_names = _get_step_names(graph)
    package_type = config.lambda_cfg.package_type
    module_name = _get_module_name(graph)

    for step_name in step_names:
        env_vars = {
            "Variables": {
                "LOKKI_S3_BUCKET": "lokki",
                "LOKKI_FLOW_NAME": graph.name,
                "LOKKI_AWS_ENDPOINT": "http://host.docker.internal:4566",
                "LOKKI_STEP_NAME": step_name,
                "LOKKI_MODULE_NAME": f"{module_name}_example",
            }
        }
        env_vars["Variables"].update(config.lambda_cfg.env)

        if package_type == "zip":
            resources[_to_pascal(step_name) + "Function"] = {
                "Type": "AWS::Serverless::Function",
                "Properties": {
                    "FunctionName": f"{graph.name}-{step_name}",
                    "Runtime": "python3.13",
                    "Handler": "handler.lambda_handler",
                    "CodeUri": "lambdas/function.zip",
                    "Timeout": config.lambda_cfg.timeout,
                    "MemorySize": config.lambda_cfg.memory,
                    "Environment": env_vars,
                },
            }
        else:
            resources[_to_pascal(step_name) + "Function"] = {
                "Type": "AWS::Serverless::Function",
                "Properties": {
                    "FunctionName": f"{graph.name}-{step_name}",
                    "Runtime": "python3.13",
                    "PackageType": "Image",
                    "ImageUri": f"lokki:{config.lambda_cfg.image_tag}",
                    "Timeout": config.lambda_cfg.timeout,
                    "MemorySize": config.lambda_cfg.memory,
                    "Environment": env_vars,
                },
            }

    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": f"Lokki flow: {graph.name} (SAM for local testing)",
        "Resources": resources,
        "Outputs": {},
    }

    return yaml.dump(template, default_flow_style=False, sort_keys=False)


def _get_step_names(graph: FlowGraph) -> set[str]:
    """Extract unique step names from graph."""
    names = set()
    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            names.add(entry.node.name)
        elif isinstance(entry, MapOpenEntry):
            names.add(entry.source.name)
            for step in entry.inner_steps:
                names.add(step.name)
        elif isinstance(entry, MapCloseEntry):
            names.add(entry.agg_step.name)
    return names


def _to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def _get_module_name(graph: FlowGraph) -> str:
    """Get the module name from the flow graph name."""
    return graph.name.replace("-", "_")
