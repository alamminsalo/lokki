"""Unit tests for CloudFormation builder module."""

import yaml

import pytest

from lokki._utils import to_pascal
from lokki.builder.cloudformation import _get_tags, _has_batch_steps, build_template
from lokki.config import LokkiConfig
from lokki.decorators import step
from lokki.graph import FlowGraph
from tests.conftest import create_build_dir


class TestGetTags:
    """Tests for _get_tags helper function."""

    def test_get_tags_structure(self) -> None:
        """Test _get_tags returns correct structure."""
        tags = _get_tags("my-flow")

        assert len(tags) == 2
        assert {"Key": "lokki:managed", "Value": "true"} in tags
        assert {"Key": "lokki:flow-name", "Value": "my-flow"} in tags

    def test_get_tags_with_different_flow_name(self) -> None:
        """Test _get_tags with different flow names."""
        tags = _get_tags("test-flow-123")

        assert tags[0]["Value"] == "true"
        assert tags[1]["Value"] == "test-flow-123"


class TestHasBatchSteps:
    """Tests for _has_batch_steps helper function."""

    def test_no_batch_steps(self) -> None:
        """Test _has_batch_steps returns False for lambda-only flow."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        assert _has_batch_steps(graph) is False

    def test_single_batch_step(self) -> None:
        """Test _has_batch_steps returns True with single batch step."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="test-flow", head=batch_step)

        assert _has_batch_steps(graph) is True

    def test_mixed_lambda_and_batch(self) -> None:
        """Test _has_batch_steps with mixed lambda and batch steps."""

        @step
        def lambda_step() -> None:
            pass

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        lambda_step().next(batch_step)
        graph = FlowGraph(name="test-flow", head=batch_step)

        assert _has_batch_steps(graph) is True


class TestBuildTemplateLambdaOnly:
    """Tests for build_template with Lambda-only flows."""

    def test_template_basic_structure(self) -> None:
        """Test basic CloudFormation template structure."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)

        assert "AWSTemplateFormatVersion" in template
        assert "Description" in template
        assert "Parameters" in template
        assert "Resources" in template
        assert "Outputs" in template

    def test_template_description(self) -> None:
        """Test template includes flow name in description."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="my-test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        assert template["Description"] == "Lokki flow: my-test-flow"

    def test_lambda_only_no_batch_params(self) -> None:
        """Test Lambda-only flow doesn't include Batch parameters."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        params = template["Parameters"]

        assert "FlowName" in params
        assert "S3Bucket" in params
        assert "BatchJobQueue" not in params
        assert "BatchJobDefinitionName" not in params

    def test_lambda_only_no_batch_resources(self) -> None:
        """Test Lambda-only flow doesn't include Batch resources."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        assert "LambdaExecutionRole" in resources
        assert "StepFunctionsExecutionRole" in resources
        assert "BatchExecutionRole" not in resources
        assert "BatchJobDefinition" not in resources


class TestBuildTemplateBatchOnly:
    """Tests for build_template with Batch-only flows."""

    def test_batch_flow_includes_batch_params(self) -> None:
        """Test Batch flow includes Batch parameters."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="batch-flow", head=batch_step)

        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        params = template["Parameters"]

        assert "BatchJobQueue" in params
        assert "BatchJobDefinitionName" in params

    def test_batch_flow_includes_batch_resources(self) -> None:
        """Test Batch flow includes Batch resources."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="batch-flow", head=batch_step)

        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        assert "BatchExecutionRole" in resources
        assert "BatchJobDefinition" in resources

    def test_batch_execution_role_policies(self) -> None:
        """Test Batch execution role has correct policies."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="batch-flow", head=batch_step)

        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        batch_role = resources["BatchExecutionRole"]
        policies = batch_role["Properties"]["Policies"]

        policy_names = [p["PolicyName"] for p in policies]
        assert "S3Access" in policy_names
        assert "LogsAccess" in policy_names

    def test_batch_job_definition(self) -> None:
        """Test Batch job definition configuration."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="batch-flow", head=batch_step)

        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        job_def = resources["BatchJobDefinition"]
        assert job_def["Type"] == "AWS::Batch::JobDefinition"
        assert job_def["Properties"]["Type"] == "container"

    def test_stepfunctions_role_batch_policy(self) -> None:
        """Test Step Functions role includes Batch access policy."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="batch-flow", head=batch_step)

        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        sfn_role = resources["StepFunctionsExecutionRole"]
        policies = sfn_role["Properties"]["Policies"]

        policy_names = [p["PolicyName"] for p in policies]
        assert "BatchAccess" in policy_names


class TestBuildTemplateMixed:
    """Tests for build_template with mixed Lambda/Batch flows."""

    def test_mixed_flow_includes_batch_resources(self) -> None:
        """Test mixed flow includes both Lambda and Batch resources."""

        @step
        def lambda_step() -> None:
            pass

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        lambda_step().next(batch_step)
        graph = FlowGraph(name="mixed-flow", head=batch_step)

        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        assert "LambdaExecutionRole" in resources
        assert "BatchExecutionRole" in resources
        assert "BatchJobDefinition" in resources


class TestBuildTemplateParameters:
    """Tests for CloudFormation parameters."""

    def test_standard_parameters(self) -> None:
        """Test standard parameters are present."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        params = template["Parameters"]

        assert "FlowName" in params
        assert "S3Bucket" in params
        assert "ECRRepoPrefix" in params
        assert "ImageTag" in params
        assert "AWSEndpoint" in params
        assert "PackageType" in params

    def test_image_tag_default(self) -> None:
        """Test ImageTag has default value."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        params = template["Parameters"]

        assert params["ImageTag"]["Default"] == "latest"

    def test_package_type_default(self) -> None:
        """Test PackageType has default value from config."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        params = template["Parameters"]

        assert params["PackageType"]["Default"] == config.lambda_cfg.package_type


class TestBuildTemplateIAMRoles:
    """Tests for IAM role generation."""

    def test_lambda_execution_role_assume_role(self) -> None:
        """Test Lambda execution role assume role policy."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        role = template["Resources"]["LambdaExecutionRole"]

        assume_role = role["Properties"]["AssumeRolePolicyDocument"]
        assert assume_role["Version"] == "2012-10-17"

        statement = assume_role["Statement"][0]
        assert statement["Effect"] == "Allow"
        assert statement["Principal"]["Service"] == "lambda.amazonaws.com"
        assert "sts:AssumeRole" in statement["Action"]

    def test_lambda_execution_role_s3_policy(self) -> None:
        """Test Lambda execution role S3 access policy."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        role = template["Resources"]["LambdaExecutionRole"]

        policies = role["Properties"]["Policies"]
        s3_policy = next(p for p in policies if p["PolicyName"] == "S3Access")

        actions = s3_policy["PolicyDocument"]["Statement"][0]["Action"]
        assert "s3:GetObject" in actions
        assert "s3:PutObject" in actions
        assert "s3:HeadObject" in actions

    def test_stepfunctions_role_assume_role(self) -> None:
        """Test Step Functions execution role assume role policy."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        role = template["Resources"]["StepFunctionsExecutionRole"]

        assume_role = role["Properties"]["AssumeRolePolicyDocument"]
        statement = assume_role["Statement"][0]

        assert statement["Principal"]["Service"] == "states.amazonaws.com"

    def test_stepfunctions_role_lambda_invoke_policy(self) -> None:
        """Test Step Functions role Lambda invoke policy."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        role = template["Resources"]["StepFunctionsExecutionRole"]

        policies = role["Properties"]["Policies"]
        lambda_policy = next(p for p in policies if p["PolicyName"] == "LambdaInvoke")

        actions = lambda_policy["PolicyDocument"]["Statement"][0]["Action"]
        assert "lambda:InvokeFunction" in actions


class TestBuildTemplateOutputs:
    """Tests for CloudFormation outputs."""

    def test_standard_outputs(self) -> None:
        """Test standard outputs are present."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        outputs = template["Outputs"]

        assert "StateMachineArn" in outputs
        assert "StateMachineName" in outputs

    def test_state_machine_arn_output(self) -> None:
        """Test StateMachineArn output configuration."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        output = template["Outputs"]["StateMachineArn"]

        assert "Description" in output
        assert "Value" in output

    def test_state_machine_name_output(self) -> None:
        """Test StateMachineName output configuration."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        output = template["Outputs"]["StateMachineName"]

        assert output["Description"] == "Step Functions State Machine Name"


class TestBuildTemplateWithSecrets:
    """Tests for build_template with AWS Secrets Manager integration."""

    def test_template_with_secrets_lambda_env_vars(self) -> None:
        """Test that secrets are added to Lambda environment variables."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        db_pwd_arn = "arn:aws:secretsmanager:us-east-1:123:secret:my-db-password"
        api_key_arn = (
            "arn:aws:secretsmanager:us-east-1:123:secret:my-api-config"
            ":SecretString:api_key"
        )
        config = LokkiConfig.from_dict(
            {
                "secrets": {
                    "secret_arns": {"DB_PASSWORD": db_pwd_arn, "API_KEY": api_key_arn}
                }
            }
        )
        template_str = build_template(graph, config, "test_module", create_build_dir())
        template = yaml.safe_load(template_str)

        step1_func = template["Resources"]["Step1Function"]["Properties"]
        env_vars = step1_func["Environment"]["Variables"]

        assert "DB_PASSWORD" in env_vars
        assert "API_KEY" in env_vars
        assert "secretsmanager" in env_vars["DB_PASSWORD"]
        assert "secretsmanager" in env_vars["API_KEY"]

    def test_template_with_secrets_iam_policy(self) -> None:
        """Test that IAM policy is added for Secrets Manager access."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        db_pwd_arn = "arn:aws:secretsmanager:us-east-1:123:secret:my-db-password"
        config = LokkiConfig.from_dict(
            {"secrets": {"secret_arns": {"DB_PASSWORD": db_pwd_arn}}}
        )
        template_str = build_template(graph, config, "test_module", create_build_dir())
        template = yaml.safe_load(template_str)

        lambda_role = template["Resources"]["LambdaExecutionRole"]["Properties"]
        policies = lambda_role["Policies"]

        secrets_policy = None
        for policy in policies:
            if policy["PolicyName"] == "SecretsManagerAccess":
                secrets_policy = policy
                break

        assert secrets_policy is not None
        assert secrets_policy["PolicyDocument"]["Statement"][0]["Action"] == [
            "secretsmanager:GetSecretValue"
        ]
        assert (
            db_pwd_arn in secrets_policy["PolicyDocument"]["Statement"][0]["Resource"]
        )

    def test_template_without_secrets_no_policy(self) -> None:
        """Test that no Secrets Manager policy is added when no secrets configured."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())
        template = yaml.safe_load(template_str)

        lambda_role = template["Resources"]["LambdaExecutionRole"]["Properties"]
        policies = lambda_role["Policies"]

        for policy in policies:
            assert policy["PolicyName"] != "SecretsManagerAccess"

    def test_template_with_secrets_batch_env_vars(self) -> None:
        """Test that secrets are added to Batch environment variables."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="test-flow", head=batch_step)
        db_pwd_arn = "arn:aws:secretsmanager:us-east-1:123:secret:my-db-password"
        config = LokkiConfig.from_dict(
            {"secrets": {"secret_arns": {"DB_PASSWORD": db_pwd_arn}}}
        )
        template_str = build_template(graph, config, "test_module", create_build_dir())
        template = yaml.safe_load(template_str)

        batch_job_def = template["Resources"]["BatchJobDefinition"]["Properties"]
        env_vars = batch_job_def["ContainerProperties"]["Environment"]

        db_password_env = None
        for env_var in env_vars:
            if env_var["Name"] == "DB_PASSWORD":
                db_password_env = env_var
                break

        assert db_password_env is not None
        assert "secretsmanager" in db_password_env["Value"]

    def test_template_with_secrets_batch_iam_policy(self) -> None:
        """Test that IAM policy is added for Batch Secrets Manager access."""

        @step(job_type="batch")
        def batch_step() -> None:
            pass

        @step
        def get_items() -> list[str]:
            return ["a"]

        get_items().map(batch_step).agg(batch_step)
        graph = FlowGraph(name="test-flow", head=batch_step)
        db_pwd_arn = "arn:aws:secretsmanager:us-east-1:123:secret:my-db-password"
        config = LokkiConfig.from_dict(
            {"secrets": {"secret_arns": {"DB_PASSWORD": db_pwd_arn}}}
        )
        template_str = build_template(graph, config, "test_module", create_build_dir())
        template = yaml.safe_load(template_str)

        batch_role = template["Resources"]["BatchExecutionRole"]["Properties"]
        policies = batch_role["Policies"]

        secrets_policy = None
        for policy in policies:
            if policy["PolicyName"] == "SecretsManagerAccess":
                secrets_policy = policy
                break

        assert secrets_policy is not None
        assert secrets_policy["PolicyDocument"]["Statement"][0]["Action"] == [
            "secretsmanager:GetSecretValue"
        ]
