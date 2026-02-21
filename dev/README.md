# Development Tools

This directory contains tools for local development and testing.

## Services

### LocalStack
Full local AWS stack for testing deployment.

### PyPI Server
Local PyPI server for testing package installation in Lambda containers.

## Quick Start

```bash
# Start all services
docker-compose up -d

# Wait for services to be ready (check health)
docker-compose ps

# Publish lokki to local PyPI
./publish.sh

# Or with custom host
PYPI_HOST=localhost:8080 ./publish.sh
```

## Local Integration Testing

This section describes how to run a full integration test of your lokki flow locally using LocalStack and SAM CLI.

### Prerequisites

1. **LocalStack running** - Start LocalStack:
   ```bash
   cd dev
   docker-compose up -d
   ```

2. **AWS CLI configured** - Ensure AWS CLI is installed and configured:
   ```bash
   export AWS_ACCESS_KEY_ID=test
   export AWS_SECRET_ACCESS_KEY=test
   export AWS_DEFAULT_REGION=us-east-1
   ```

### Step 1: Configure for LocalStack

Create or update `lokki.yml` in your project:

```yaml
aws:
  endpoint: http://localhost:4566
  artifact_bucket: lokki
  ecr_repo_prefix: ""

lambda:
  package_type: zip
  timeout: 900
  memory: 512
```

### Step 2: Build the Flow

```bash
python flow_script.py build
```

This generates:
- `lokki-build/lambdas/function.zip` - Lambda package
- `lokki-build/statemachine.json` - Step Functions state machine
- `lokki-build/sam.yaml` - SAM template for local testing
- `lokki-build/template.yaml` - CloudFormation template

### Step 3: Deploy to LocalStack

```bash
python flow_script.py deploy --stack-name lokki-test
```

This will:
1. Skip Docker image push (ZIP deployment)
2. Deploy Lambda functions to LocalStack
3. Deploy IAM roles

### Step 4: Test Individual Lambda Functions

Test a specific Lambda function locally:

```bash
cd lokki-build
sam local invoke GetBirdsFunction --template sam.yaml --region us-east-1
```

Expected output:
```
[INFO] Lambda invoked: flow=birds-flow, step=get_birds, run_id=unknown
[INFO] Step completed: get_birds in 5.461s
{"map_manifest_key": "lokki/birds-flow/unknown/get_birds/map_manifest.json", "run_id": "unknown"}
```

### Step 5: Verify Outputs in S3

Check what was written to LocalStack S3:

```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://lokki/ --recursive
```

Expected output:
```
lokki/birds-flow/unknown/get_birds/0/output.pkl.gz
lokki/birds-flow/unknown/get_birds/1/output.pkl.gz
lokki/birds-flow/unknown/get_birds/2/output.pkl.gz
lokki/birds-flow/unknown/get_birds/map_manifest.json
lokki/birds-flow/unknown/get_birds/output.pkl.gz
```

### Step 6: Run Full Pipeline with Step Functions

To run the complete pipeline, create the state machine manually:

```bash
# Create the state machine
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  stepfunctions create-state-machine \
  --name birds-flow \
  --definition file://lokki-build/statemachine.json \
  --role-arn arn:aws:iam::123456789:role/test
```

Note: The role ARN is a placeholder for LocalStack - it doesn't validate the role.

Then start an execution:

```bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:000000000000:stateMachine:birds-flow \
  --input '{"bucket": "lokki"}'
```

### Available Dev Scripts

Use the provided scripts for common workflows:

```bash
# Deploy and test individual functions
./dev/deploy-localstack.sh

# Test Lambda functions only
./dev/test-sam-local.sh
```

## Alternative: Path-based development

For development without a local PyPI server, use a path reference:

```toml
[project]
dependencies = [
    "lokki@../lokki",
]
```

Note: This requires the path to be accessible during Docker build (e.g., via a volume mount).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYPI_HOST` | `localhost:8080` | PyPI server host:port |

## Configuration

Make sure your `lokki.yml` has the correct settings for LocalStack:

```yaml
aws:
  artifact_bucket: lokki-artifacts
  endpoint: http://localhost:4566
  ecr_repo_prefix: ""  # Use local Docker images

lambda:
  package_type: zip
  timeout: 60
  memory: 256
  image_tag: latest
  env:
    LOG_LEVEL: DEBUG
```

## Notes

- LocalStack's S3 endpoint: `http://localhost:4566`
- When using local Docker images (empty `ecr_repo_prefix`), Lambda functions will use local image names
- The Lambda runtime inside containers needs to reach the PyPI server at `host.docker.internal:8080`
- SAM local invoke uses `http://host.docker.internal:4566` to reach LocalStack from the container
