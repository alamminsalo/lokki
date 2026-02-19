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

    step_names = _get_step_names(graph)
    for step_name in step_names:
        resources[_to_pascal(step_name) + "Function"] = {
            "Type": "AWS::Lambda::Function",
            "Properties": {
                "FunctionName": "{{Param:FlowName}}-" + step_name,
                "PackageType": "Image",
                "Code": {
                    "ImageUri": "{{Param:ECRRepoPrefix}}/"
                    + step_name
                    + ":{{Param:ImageTag}}"
                },
                "Role": "{{GetAtt:LambdaExecutionRole.Arn}}",
                "Timeout": config.lambda_defaults.timeout,
                "MemorySize": config.lambda_defaults.memory,
                "Environment": {
                    "Variables": {
                        "LOKKI_S3_BUCKET": "{{Param:S3Bucket}}",
                        "LOKKI_FLOW_NAME": "{{Param:FlowName}}",
                        **config.lambda_env,
                    }
                },
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
