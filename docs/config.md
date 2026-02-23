# Configuration Reference

This document lists all configurable options for lokki, including settings for AWS, Lambda, Batch, and logging.

---

## Configuration File: `lokki.toml`

lokki reads configuration from a `lokki.toml` file in your project root. You can also use a global config at `~/.lokki/lokki.toml` which is merged with the local config.

### Configuration Precedence

Configuration values are resolved in the following order (highest to lowest):

1. Environment variables
2. Local `lokki.toml`
3. Global `~/.lokki/lokki.toml`
4. Default values

---

## Top-Level Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `build_dir` | `str` | `"lokki-build"` | Output directory for build artifacts |

---

## AWS Configuration `[aws]`

| Setting | Type | Default | Environment Variable | Description |
|---------|------|---------|---------------------|-------------|
| `artifact_bucket` | `str` | `""` | `LOKKI_ARTIFACT_BUCKET` | S3 bucket for pipeline data and artifacts |
| `image_repository` | `str` | `""` | `LOKKI_IMAGE_REPOSITORY` | Docker repository (`local`, `docker.io`, or ECR prefix) |
| `region` | `str` | `"us-east-1"` | `LOKKI_AWS_REGION` | AWS region for deployments |
| `endpoint` | `str` | `""` | `LOKKI_AWS_ENDPOINT` | AWS endpoint for local development (e.g., LocalStack) |
| `stepfunctions_role` | `str` | `""` | - | ARN of existing Step Functions execution role |
| `lambda_execution_role` | `str` | `""` | - | ARN of existing Lambda execution role |

---

## Lambda Configuration `[lambda]`

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `package_type` | `str` | `"image"` | Deployment type: `"image"` (Docker) or `"zip"` |
| `base_image` | `str` | `"public.ecr.aws/lambda/python:3.13"` | Docker base image for Lambda functions |
| `timeout` | `int` | `900` | Lambda timeout in seconds |
| `memory` | `int` | `512` | Lambda memory in MB |
| `image_tag` | `str` | `"latest"` | Docker image tag for Lambda functions |

### Lambda Environment Variables `[lambda.env]`

Custom environment variables injected into every Lambda function:

```toml
[lambda.env]
LOG_LEVEL = "INFO"
MY_API_ENDPOINT = "https://api.example.com"
```

---

## Batch Configuration `[batch]`

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `job_queue` | `str` | `""` | AWS Batch job queue name |
| `job_definition_name` | `str` | `""` | Base name for job definitions |
| `base_image` | `str` | `"python:3.11-slim"` | Docker base image for Batch jobs |
| `timeout_seconds` | `int` | `3600` | Default job timeout in seconds |
| `vcpu` | `int` | `2` | Default number of vCPUs for jobs |
| `memory_mb` | `int` | `4096` | Default memory in MB for jobs |
| `image` | `str` | `""` | Docker image for jobs (defaults to Lambda image if empty) |

### Batch Environment Variables `[batch.env]`

Custom environment variables injected into every Batch job:

```toml
[batch.env]
MY_VAR = "value"
```

---

## Logging Configuration `[logging]`

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `level` | `str` | `"INFO"` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `format` | `str` | `"human"` | Log format: `"human"` or `"json"` |
| `progress_interval` | `int` | `10` | Map progress update interval (items or 10%, whichever is smaller) |
| `show_timestamps` | `bool` | `true` | Include ISO timestamps in log output |

---

## Example Configuration

### Minimal Configuration

```toml
[aws]
artifact_bucket = "my-lokki-bucket"
region = "us-west-2"
```

### Full Configuration

```toml
# lokki.toml

# Build output directory
build_dir = "lokki-build"

[aws]
artifact_bucket = "my-lokki-artifacts"
image_repository = "123456789.dkr.ecr.us-west-2.amazonaws.com/myproject"
region = "us-west-2"
endpoint = ""  # Use empty for real AWS, "http://localhost:4566" for LocalStack
stepfunctions_role = "arn:aws:iam::123456789:role/lokki-sfn-role"
lambda_execution_role = "arn:aws:iam::123456789:role/lokki-lambda-role"

[lambda]
package_type = "image"
base_image = "public.ecr.aws/lambda/python:3.13"
timeout = 900
memory = 512
image_tag = "v1.0.0"

[lambda.env]
LOG_LEVEL = "INFO"

[batch]
job_queue = "my-batch-queue"
job_definition_name = "lokki-jobs"
base_image = "python:3.11-slim"
timeout_seconds = 3600
vcpu = 4
memory_mb = 8192

[batch.env]
BATCH_VAR = "value"

[logging]
level = "DEBUG"
format = "json"
progress_interval = 20
show_timestamps = true
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `LOKKI_ARTIFACT_BUCKET` | S3 bucket for pipeline data |
| `LOKKI_IMAGE_REPOSITORY` | Docker repository |
| `LOKKI_AWS_REGION` | AWS region |
| `LOKKI_AWS_ENDPOINT` | AWS endpoint for local development |
| `LOKKI_BUILD_DIR` | Build output directory |
| `LOKKI_LOG_LEVEL` | Logging level |
| `LOKKI_BATCH_JOB_QUEUE` | AWS Batch job queue |
| `LOKKI_BATCH_JOB_DEFINITION` | AWS Batch job definition |

---

## Step-Level Overrides

Individual steps can override some Lambda/Batch settings using decorator parameters:

```python
from lokki import step

@step
def lambda_step(data):
    """Runs as Lambda with default settings"""
    return process(data)

@step(job_type="batch", vcpu=8, memory_mb=16384, timeout_seconds=1800)
def batch_step(data):
    """Runs as Batch with custom resources"""
    return heavy_processing(data)
```

### Step-Level Settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `job_type` | `str` | `"lambda"` | Execution backend: `"lambda"` or `"batch"` |
| `vcpu` | `int \| None` | `None` | vCPUs (uses config default if `None`) |
| `memory_mb` | `int \| None` | `None` | Memory in MB (uses config default if `None`) |
| `timeout_seconds` | `int \| None` | `None` | Timeout in seconds (uses config default if `None`) |
| `retry` | `dict` | `{}` | Retry configuration |

### Retry Configuration

```python
@step(retry={"retries": 3, "delay": 2, "backoff": 1.5})
def unreliable_step(data):
    """Retries up to 3 times with exponential backoff"""
    return may_fail(data)
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `retries` | `int` | `0` | Maximum retry attempts |
| `delay` | `float` | `1.0` | Initial delay in seconds |
| `backoff` | `float` | `1.0` | Exponential backoff multiplier |
| `max_delay` | `float` | `60.0` | Maximum delay cap in seconds |
| `exceptions` | `list[type]` | `[Exception]` | Exception types to catch |
