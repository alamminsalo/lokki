"""CloudFormation template generation."""

from __future__ import annotations

from typing import Any

import yaml

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def build_template(
    graph: FlowGraph,
    config: LokkiConfig,
    module_name: str,
) -> str:
    """Build a CloudFormation template for the flow."""
    resources: dict[str, dict[str, Any]] = {}

    parameters = {
        "FlowName": {"Type": "String"},
        "S3Bucket": {"Type": "String"},
        "ECRRepoPrefix": {"Type": "String"},
        "ImageTag": {"Type": "String", "Default": "latest"},
        "AWSEndpoint": {"Type": "String", "Default": ""},
        "PackageType": {"Type": "String", "Default": config.lambda_cfg.package_type},
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
                                    {
                                        "Fn::Sub": (
                                            "arn:aws:s3:::${S3Bucket}/lokki/${FlowName}/*"
                                        )
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        },
    }

    step_names = _get_step_names(graph)
    package_type = config.lambda_cfg.package_type

    for step_name in step_names:
        env_vars = {
            "LOKKI_S3_BUCKET": {"Ref": "S3Bucket"},
            "LOKKI_FLOW_NAME": {"Ref": "FlowName"},
            "LOKKI_AWS_ENDPOINT": {"Ref": "AWSEndpoint"},
            "LOKKI_STEP_NAME": step_name,
            "LOKKI_MODULE_NAME": module_name,
        }
        env_vars.update(config.lambda_cfg.env)

        if package_type == "zip":
            resources[_to_pascal(step_name) + "Function"] = {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "FunctionName": {"Fn::Sub": "${FlowName}-" + step_name},
                    "PackageType": "ZipFile",
                    "Code": {
                        "S3Bucket": {"Ref": "S3Bucket"},
                        "S3Key": {"Fn::Sub": "lokki/${FlowName}/lambdas/function.zip"},
                    },
                    "Role": {"Fn::GetAtt": ["LambdaExecutionRole", "Arn"]},
                    "Timeout": config.lambda_cfg.timeout,
                    "MemorySize": config.lambda_cfg.memory,
                    "Environment": {"Variables": env_vars},
                    "Handler": "handler.lambda_handler",
                },
            }
        else:
            resources[_to_pascal(step_name) + "Function"] = {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "FunctionName": {"Fn::Sub": "${FlowName}-" + step_name},
                    "PackageType": "Image",
                    "Code": {
                        "ImageUri": {"Fn::Sub": "${ECRRepoPrefix}/lokki:${ImageTag}"}
                    },
                    "Role": {"Fn::GetAtt": ["LambdaExecutionRole", "Arn"]},
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
                                    {
                                        "Fn::Sub": (
                                            "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:"
                                            "function:${FlowName}-*"
                                        )
                                    }
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
                                    {
                                        "Fn::Sub": (
                                            "arn:aws:s3:::${S3Bucket}/lokki/${FlowName}/*"
                                        )
                                    }
                                ],
                            }
                        ],
                    },
                },
            ],
        },
    }

    resources["StateMachine"] = {
        "Type": "AWS::StepFunctions::StateMachine",
        "Properties": {
            "DefinitionS3Location": {
                "Bucket": {"Ref": "S3Bucket"},
                "Key": {"Fn::Sub": "lokki/${FlowName}/statemachine.json"},
            },
            "RoleArn": {"Fn::GetAtt": ["StepFunctionsExecutionRole", "Arn"]},
            "StateMachineName": {"Fn::Sub": "${FlowName}"},
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
    return graph.name.replace("-", "_")
