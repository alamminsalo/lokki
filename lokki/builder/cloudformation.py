"""CloudFormation template generation."""

from __future__ import annotations

from typing import Any

import yaml

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def build_template(graph: FlowGraph, config: LokkiConfig) -> str:
    """Build a CloudFormation template for the flow."""
    resources: dict[str, dict[str, Any]] = {}

    parameters = {
        "FlowName": {"Type": "String"},
        "S3Bucket": {"Type": "String"},
        "ECRRepoPrefix": {"Type": "String"},
        "ImageTag": {"Type": "String", "Default": "latest"},
        "AWSEndpoint": {"Type": "String", "Default": ""},
    }

    resources["LambdaExecutionRole"] = {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            },
            "ManagedPolicyArns": [
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
            ],
            "Policies": [
                {
                    "PolicyName": "S3Access",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["s3:GetObject", "s3:PutObject"],
                                "Resource": [
                                    "arn:aws:s3:::"
                                    + "{{Param:S3Bucket}}"
                                    + "/lokki/"
                                    + "{{Param:FlowName}}"
                                    + "/*"
                                ],
                            }
                        ],
                    },
                }
            ],
        },
    }

    module_name = _get_module_name(graph)

    step_names = _get_step_names(graph)
    for step_name in step_names:
        env_vars = {
            "LOKKI_S3_BUCKET": "{{Param:S3Bucket}}",
            "LOKKI_FLOW_NAME": "{{Param:FlowName}}",
            "LOKKI_AWS_ENDPOINT": "{{Param:AWSEndpoint}}",
            "LOKKI_STEP_NAME": step_name,
            "LOKKI_MODULE_NAME": module_name,
        }
        env_vars.update(config.lambda_cfg.env)

        resources[_to_pascal(step_name) + "Function"] = {
            "Type": "AWS::Lambda::Function",
            "Properties": {
                "FunctionName": "{{Param:FlowName}}-" + step_name,
                "PackageType": "Image",
                "Code": {
                    "ImageUri": "{{Param:ECRRepoPrefix}}/lokki:{{Param:ImageTag}}"
                },
                "Role": "{{GetAtt:LambdaExecutionRole.Arn}}",
                "Timeout": config.lambda_cfg.timeout,
                "MemorySize": config.lambda_cfg.memory,
                "Environment": {"Variables": env_vars},
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
            "Policies": [
                {
                    "PolicyName": "LambdaInvoke",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["lambda:InvokeFunction"],
                                "Resource": [
                                    "arn:aws:lambda:${{AWS::Region}}:${{AWS::AccountId}}:function:{{Param:FlowName}}-*"
                                ],
                            }
                        ],
                    },
                },
                {
                    "PolicyName": "S3MapResults",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["s3:GetObject", "s3:PutObject"],
                                "Resource": [
                                    "arn:aws:s3:::{{Param:S3Bucket}}/lokki/{{Param:FlowName}}/*"
                                ],
                            }
                        ],
                    },
                },
            ],
        },
    }

    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": f"Lokki flow: {graph.name}",
        "Parameters": parameters,
        "Resources": resources,
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
    return f"{graph.name.replace('-', '_')}_flow"
