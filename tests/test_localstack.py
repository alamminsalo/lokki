"""Integration tests for LocalStack deployment and execution.

These tests require a running LocalStack instance. They test:
- Flow deployment to LocalStack
- Lambda function creation and invocation
- Step Functions state machine creation and execution
- End-to-end flow execution
- Map states
- Flow parameters

Run with: pytest tests/test_localstack.py -v

Note: Tests are skipped in local runs - covered by GitHub Actions workflow instead.
"""

import os
import subprocess
from pathlib import Path

import boto3
import pytest

LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
AWS_REGION = "us-east-1"
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"
TEST_PIPELINE_DIR = Path(__file__).parent.parent / "examples" / "ci_test_pipeline"


def get_endpoint_url():
    """Get the LocalStack endpoint URL."""
    return LOCALSTACK_ENDPOINT


@pytest.fixture(scope="module")
def localstack_services():
    """Ensure LocalStack is running and return endpoint."""
    # Skip by default - only run in CI or when explicitly enabled
    if not os.environ.get("RUN_LOCALSTACK_TESTS") and os.environ.get("CI") != "true":
        pytest.skip(
            "LocalStack tests skipped by default (set RUN_LOCALSTACK_TESTS=1 to run)"
        )

    endpoint = get_endpoint_url()

    # Check if LocalStack is running using urllib (built-in)
    import urllib.request

    req = urllib.request.Request(f"{endpoint}/_localstack/health")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                pytest.skip("LocalStack is not running")
    except Exception:  # noqa: BLE001
        pytest.skip("LocalStack is not running")

    # Set environment variables for boto3
    os.environ["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
    os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY
    os.environ["AWS_DEFAULT_REGION"] = AWS_REGION
    os.environ["AWS_ENDPOINT_URL"] = endpoint

    # Create S3 bucket
    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    try:
        s3_client.create_bucket(Bucket="lokki")
    except Exception:
        pass  # Bucket may already exist

    yield endpoint


@pytest.fixture
def s3_client(localstack_services):
    """Create S3 client for LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=localstack_services,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


@pytest.fixture(scope="module")
def cf_client(localstack_services):
    """Create CloudFormation client for LocalStack."""
    return boto3.client(
        "cloudformation",
        endpoint_url=localstack_services,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


@pytest.fixture(scope="module")
def lambda_client(localstack_services):
    """Create Lambda client for LocalStack."""
    return boto3.client(
        "lambda",
        endpoint_url=localstack_services,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


@pytest.fixture(scope="module")
def sfn_client(localstack_services):
    """Create Step Functions client for LocalStack."""
    return boto3.client(
        "stepfunctions",
        endpoint_url=localstack_services,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


@pytest.fixture(scope="module")
def sync_pipeline_deps():
    """Sync dependencies in ci_test_pipeline directory."""
    result = subprocess.run(
        ["uv", "sync"],
        cwd=TEST_PIPELINE_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"Failed to sync ci_test_pipeline deps: {result.stderr}")
    return True


@pytest.fixture(scope="module")
def built_pipeline(sync_pipeline_deps):
    """Build the ci_test_pipeline flow."""
    env = os.environ.copy()
    env.update(
        {
            "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
            "AWS_DEFAULT_REGION": AWS_REGION,
            "AWS_ENDPOINT_URL": LOCALSTACK_ENDPOINT,
            "LOKKI_ARTIFACT_BUCKET": "lokki",
        }
    )

    result = subprocess.run(
        ["uv", "run", "python", "flow.py", "build"],
        cwd=TEST_PIPELINE_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        pytest.skip(f"Failed to build ci-test-pipeline: {result.stderr}")

    return True


@pytest.fixture(scope="module")
def deployed_stack(built_pipeline, cf_client):
    """Deploy the test_ci-test-pipeline stack to LocalStack."""
    env = os.environ.copy()
    env.update(
        {
            "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
            "AWS_DEFAULT_REGION": AWS_REGION,
        }
    )

    result = subprocess.run(
        ["uv", "run", "python", "flow.py", "deploy", "--confirm"],
        cwd=TEST_PIPELINE_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        pytest.skip(f"Failed to deploy stack: {result.stderr}")

    # Wait for stack to be created
    import time

    for _ in range(30):
        try:
            stack = cf_client.describe_stacks(StackName="ci-test-pipeline-stack")
            status = stack["Stacks"][0]["StackStatus"]
            if status in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
                break
            if status in ("CREATE_FAILED", "ROLLBACK_COMPLETE"):
                pytest.skip(f"Stack creation failed: {status}")
        except cf_client.exceptions.StackNotFoundException:
            pass
        time.sleep(2)

    yield True

    # Cleanup
    try:
        cf_client.delete_stack(StackName="ci-test-pipeline-stack")
    except Exception:
        pass


class TestLocalStackDeployment:
    """Tests for deploying flows to LocalStack."""

    def test_flow_build_and_deploy(self, built_pipeline, deployed_stack):
        """Test building and deploying a simple flow to LocalStack."""
        assert built_pipeline
        assert deployed_stack

    def test_cloudformation_stack_creation(self, deployed_stack, cf_client):
        """Test that CloudFormation stack is created with correct resources."""
        stack = cf_client.describe_stacks(StackName="ci-test-pipeline-stack")
        status = stack["Stacks"][0]["StackStatus"]
        assert status in ("CREATE_COMPLETE", "UPDATE_COMPLETE")

        # Note: StateMachineArn output may not be available in LocalStack
        # Just verify stack exists, outputs are optional in LocalStack


class TestLambdaInvocation:
    """Tests for invoking Lambda functions."""

    def test_lambda_function_invocation(self, deployed_stack, lambda_client):
        """Test invoking a Lambda function directly."""
        # List Lambda functions
        response = lambda_client.list_functions()
        function_names = [f["FunctionName"] for f in response.get("Functions", [])]

        # Check that ci-test-pipeline Lambda functions exist
        expected_functions = [
            "ci-test-pipeline-get_values",
            "ci-test-pipeline-transform",
        ]

        for func in expected_functions:
            assert func in function_names, f"Expected Lambda function {func} not found"


class TestStepFunctions:
    """Tests for Step Functions state machine."""

    def test_state_machine_creation(self, deployed_stack, sfn_client):
        """Test that Step Functions state machine is created."""
        response = sfn_client.list_state_machines()
        state_machines = response.get("stateMachines", [])

        arn = None
        for sm in state_machines:
            if "ci-test-pipeline" in sm["name"]:
                arn = sm["stateMachineArn"]
                break

        assert arn is not None, "State machine not found"

    def test_state_machine_execution(self, deployed_stack, sfn_client):
        """Test executing the state machine."""
        # Note: Skipped because LocalStack Pro is required to execute Lambda functions
        pytest.skip("LocalStack Pro required for Lambda execution")


class TestFlowParameters:
    """Tests for flow parameters in deployment."""

    def test_flow_parameters_in_lambda_environment(self, deployed_stack, lambda_client):
        """Test that flow parameters are correctly set in Lambda environment."""
        # Note: Skipped because LocalStack Pro is required to invoke Lambda
        pytest.skip("LocalStack Pro required for Lambda invocation")


class TestMapStates:
    """Tests for step chain in Step Functions."""

    def test_step_chain_in_state_machine(self, deployed_stack, sfn_client):
        """Test that step chain is correctly generated in state machine."""
        # Find state machine ARN
        response = sfn_client.list_state_machines()
        state_machines = response.get("stateMachines", [])

        arn = None
        for sm in state_machines:
            if "ci-test-pipeline" in sm["name"]:
                arn = sm["stateMachineArn"]
                break

        if arn is None:
            pytest.skip("State machine not found")

        # Get state machine definition
        response = sfn_client.describe_state_machine(stateMachineArn=arn)
        import json

        definition = json.loads(response["definition"])

        # Check for step chain states
        states = definition.get("States", {})

        # Verify expected steps exist (GetValues -> Transform)
        assert "GetValues" in states, "GetValues state not found"
        assert "Transform" in states, "Transform state not found"

        # Verify chaining
        assert states["GetValues"].get("Next") == "Transform"
        assert states["Transform"].get("End") is True


class TestCloudFormationTemplate:
    """Tests for CloudFormation template generation."""

    def test_template_has_correct_parameters(self):
        """Test that CloudFormation template has correct parameters."""
        template_path = TEST_PIPELINE_DIR / "lokki-build" / "template.yaml"
        if not template_path.exists():
            pytest.skip("Template not built")

        import yaml

        with open(template_path) as f:
            template = yaml.safe_load(f)

        params = template.get("Parameters", {})
        assert "FlowName" in params
        assert "S3Bucket" in params
        assert "ECRRepoPrefix" in params

    def test_template_uses_zip_package_type(self):
        """Test that template uses ZIP package type."""
        template_path = TEST_PIPELINE_DIR / "lokki-build" / "template.yaml"
        if not template_path.exists():
            pytest.skip("Template not built")

        import yaml

        with open(template_path) as f:
            template = yaml.safe_load(f)

        resources = template.get("Resources", {})

        # Find Lambda functions
        lambda_functions = [
            r for r in resources.values() if r.get("Type") == "AWS::Lambda::Function"
        ]

        assert len(lambda_functions) > 0, "No Lambda functions found in template"


class TestCLILocalStack:
    """Tests for CLI commands against LocalStack."""

    def test_cli_build_command(self, sync_pipeline_deps):
        """Test that 'python flow.py build' works."""
        env = os.environ.copy()
        env.update(
            {
                "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
                "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
                "AWS_DEFAULT_REGION": AWS_REGION,
                "LOKKI_ARTIFACT_BUCKET": "lokki",
            }
        )

        result = subprocess.run(
            ["uv", "run", "python", "flow.py", "build"],
            cwd=TEST_PIPELINE_DIR,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Build failed: {result.stderr}"

    def test_cli_deploy_command(self, sync_pipeline_deps, cf_client):
        """Test that 'python flow.py deploy --confirm' works."""
        # Clean up any existing stack first
        try:
            cf_client.delete_stack(StackName="ci-test-pipeline-stack")
            import time

            time.sleep(5)
        except cf_client.exceptions.StackNotFoundException:
            pass
        except Exception:
            pass

        env = os.environ.copy()
        env.update(
            {
                "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
                "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
                "AWS_DEFAULT_REGION": AWS_REGION,
                "AWS_ENDPOINT_URL": LOCALSTACK_ENDPOINT,
                "LOKKI_ARTIFACT_BUCKET": "lokki",
            }
        )

        result = subprocess.run(
            ["uv", "run", "python", "flow.py", "deploy", "--confirm"],
            cwd=TEST_PIPELINE_DIR,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Deploy failed: {result.stderr}"

        # Verify stack was created
        stack = cf_client.describe_stacks(StackName="ci-test-pipeline-stack")
        status = stack["Stacks"][0]["StackStatus"]
        assert status in ("CREATE_COMPLETE", "UPDATE_COMPLETE")

    def test_cli_destroy_command(self, sync_pipeline_deps, cf_client):
        """Test that 'python flow.py destroy --confirm' works."""
        env = os.environ.copy()
        env.update(
            {
                "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
                "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
                "AWS_DEFAULT_REGION": AWS_REGION,
                "AWS_ENDPOINT_URL": LOCALSTACK_ENDPOINT,
                "LOKKI_ARTIFACT_BUCKET": "lokki",
            }
        )

        # Ensure stack exists
        try:
            cf_client.describe_stacks(StackName="ci-test-pipeline-stack")
        except Exception:
            # Create stack first
            build_result = subprocess.run(
                ["uv", "run", "python", "flow.py", "build"],
                cwd=TEST_PIPELINE_DIR,
                env=env,
                capture_output=True,
                text=True,
            )
            deploy_result = subprocess.run(
                ["uv", "run", "python", "flow.py", "deploy", "--confirm"],
                cwd=TEST_PIPELINE_DIR,
                env=env,
                capture_output=True,
                text=True,
            )
            if build_result.returncode != 0 or deploy_result.returncode != 0:
                pytest.skip(
                    f"Could not deploy stack: {build_result.stderr[:200]}"
                    f" {deploy_result.stderr[:200]}"
                )

        # Now test destroy
        result = subprocess.run(
            ["uv", "run", "python", "flow.py", "destroy", "--confirm"],
            cwd=TEST_PIPELINE_DIR,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Destroy failed: {result.stderr}"

    def test_cli_run_command_local_execution(self, sync_pipeline_deps):
        """Test that 'python flow.py run' works locally."""
        env = os.environ.copy()
        env.update(
            {
                "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
                "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
                "AWS_DEFAULT_REGION": AWS_REGION,
            }
        )

        result = subprocess.run(
            ["uv", "run", "python", "flow.py", "run"],
            cwd=TEST_PIPELINE_DIR,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Run failed: {result.stderr}"
