"""CloudFormation template generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from lokki._utils import get_step_names, to_pascal
from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def build_template(
    graph: FlowGraph,
    config: LokkiConfig,
    module_name: str,
    build_dir: Path,
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

    has_batch_steps = _has_batch_steps(graph)

    if has_batch_steps:
        parameters["BatchJobQueue"] = {
            "Type": "String",
            "Default": config.batch_cfg.job_queue,
        }
        parameters["BatchJobDefinitionName"] = {
            "Type": "String",
            "Default": config.batch_cfg.job_definition_name,
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

    step_names = get_step_names(graph)
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
            resources[to_pascal(step_name) + "Function"] = {
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
            resources[to_pascal(step_name) + "Function"] = {
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

    if has_batch_steps:
        batch_image = config.batch_cfg.image or "${ECRRepoPrefix}/lokki:${ImageTag}"
        resources["BatchExecutionRole"] = {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
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
                    },
                    {
                        "PolicyName": "LogsAccess",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": [
                                        "logs:CreateLogGroup",
                                        "logs:CreateLogStream",
                                        "logs:PutLogEvents",
                                    ],
                                    "Resource": "*",
                                }
                            ],
                        },
                    },
                ],
            },
        }

        resources["BatchJobDefinition"] = {
            "Type": "AWS::Batch::JobDefinition",
            "Properties": {
                "JobDefinitionName": {"Ref": "BatchJobDefinitionName"},
                "Type": "container",
                "ContainerProperties": {
                    "Image": {"Fn::Sub": batch_image},
                    "Vcpus": config.batch_cfg.vcpu,
                    "Memory": config.batch_cfg.memory_mb,
                    "JobRoleArn": {"Fn::GetAtt": ["BatchExecutionRole", "Arn"]},
                    "Environment": _build_batch_environment(config),
                    "LogConfiguration": {
                        "LogDriver": "awslogs",
                        "Options": {
                            "awslogs-group": "/aws/batch/${FlowName}",
                            "awslogs-region": {"Ref": "AWS::Region"},
                            "awslogs-stream-prefix": "batch",
                        },
                    },
                },
                "RetryStrategy": {"Attempts": 1},
            },
        }

        sfn_role = resources["StepFunctionsExecutionRole"]
        sfn_role["Properties"]["Policies"].append(
            {
                "PolicyName": "BatchAccess",
                "PolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "batch:SubmitJob",
                                "batch:DescribeJobs",
                                "batch:TerminateJob",
                            ],
                            "Resource": "*",
                        }
                    ],
                },
            }
        )

    state_machine_path = build_dir / "statemachine.json"
    state_machine_json = json.loads(state_machine_path.read_text())

    resources["StateMachine"] = {
        "Type": "AWS::StepFunctions::StateMachine",
        "Properties": {
            "DefinitionString": json.dumps(state_machine_json),
            "RoleArn": {"Fn::GetAtt": ["StepFunctionsExecutionRole", "Arn"]},
            "StateMachineName": {"Fn::Sub": "${FlowName}"},
        },
    }

    if graph.schedule:
        resources["EventsRole"] = {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "events.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
                "Policies": [
                    {
                        "PolicyName": "StartExecution",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": ["states:StartExecution"],
                                    "Resource": {"Fn::GetAtt": ["StateMachine", "Arn"]},
                                }
                            ],
                        },
                    }
                ],
            },
        }

        resources["ScheduleRule"] = {
            "Type": "AWS::Events::Rule",
            "Properties": {
                "Description": f"Schedule for flow: {graph.name}",
                "ScheduleExpression": graph.schedule,
                "State": "ENABLED",
                "Targets": [
                    {
                        "Id": "StateMachineTarget",
                        "Arn": {"Fn::GetAtt": ["StateMachine", "Arn"]},
                        "RoleArn": {"Fn::GetAtt": ["EventsRole", "Arn"]},
                    }
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


def _has_batch_steps(graph: FlowGraph) -> bool:
    """Check if the graph contains any Batch job steps."""
    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            if entry.job_type == "batch":
                return True
        elif isinstance(entry, MapOpenEntry):
            for step in entry.inner_steps:
                if getattr(step, "job_type", "lambda") == "batch":
                    return True
        elif isinstance(entry, MapCloseEntry):
            if getattr(entry.agg_step, "job_type", "lambda") == "batch":
                return True
    return False


def _build_batch_environment(config: LokkiConfig) -> list[dict[str, Any]]:
    """Build environment variables for Batch jobs from config."""
    env = [
        {"Name": "LOKKI_S3_BUCKET", "Value": {"Ref": "S3Bucket"}},
        {"Name": "LOKKI_FLOW_NAME", "Value": {"Ref": "FlowName"}},
        {"Name": "LOKKI_AWS_ENDPOINT", "Value": {"Ref": "AWSEndpoint"}},
    ]
    for key, value in config.batch_cfg.env.items():
        env.append({"Name": key, "Value": value})
    return env
