"""SAM template generation for local testing with sam local."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def build_sam_template(
    graph: FlowGraph, config: LokkiConfig, build_dir: Path, module_name: str
) -> str:
    """Build a SAM template for local testing with sam local."""
    resources: dict[str, dict[str, Any]] = {}

    step_names = _get_step_names(graph)
    package_type = config.lambda_cfg.package_type

    for step_name in step_names:
        env_vars = {
            "Variables": {
                "LOKKI_S3_BUCKET": "lokki",
                "LOKKI_FLOW_NAME": graph.name,
                "LOKKI_AWS_ENDPOINT": "http://host.docker.internal:4566",
                "LOKKI_STEP_NAME": step_name,
                "LOKKI_MODULE_NAME": module_name,
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

    resources["StepFunctionsExecutionRole"] = {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "states.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            },
            "ManagedPolicyArns": [
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
            ],
            "Policies": [
                {
                    "PolicyName": "InvokeLambda",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["lambda:InvokeFunction"],
                                "Resource": [
                                    f"arn:aws:lambda:us-east-1:123456789012:function:{graph.name}-*"
                                ],
                            }
                        ],
                    },
                },
                {
                    "PolicyName": "S3Access",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["s3:GetObject", "s3:PutObject"],
                                "Resource": "arn:aws:s3:::lokki/lokki/*",
                            }
                        ],
                    },
                },
            ],
        },
    }

    state_machine_path = build_dir / "statemachine.json"
    if state_machine_path.exists():
        state_machine_json = json.loads(state_machine_path.read_text())
        resources[_to_pascal(graph.name.replace("-", "")) + "StateMachine"] = {
            "Type": "AWS::Serverless::StateMachine",
            "Properties": {
                "Definition": state_machine_json,
                "Role": (
                    f"arn:aws:iam::123456789012:role/{graph.name}-stepfunctions-role"
                ),
                "Type": "STANDARD",
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
