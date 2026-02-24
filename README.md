# lokki

<p align="center">
  <img src="assets/logo.svg" width="200">
</p>

[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue)](https://pypi.org/project/lokkiflow/)
[![Test Coverage](https://img.shields.io/badge/coverage-80%25-green)](https://github.com/alamminsalo/lokki/actions)
[![Tests](https://img.shields.io/badge/tests-274%20passed-green)](https://github.com/alamminsalo/lokki/actions)

A Python library for defining, building, and deploying data pipelines to AWS Step Functions.

## Features

- **Simple Python decorators** - Define pipelines using `@step` and `@flow` decorators
- **Local execution** - Test your flows locally before deploying
- **AWS Step Functions** - Deploy to AWS Step Functions with Distributed Map for parallel processing
- **Lambda packaging** - Auto-generates Docker images or ZIP archives for each step
- **CloudFormation** - Generates complete CloudFormation templates for deployment
- **Retry configuration** - Configure automatic retries for failed steps
- **Flow parameters** - Pass parameters to flows at runtime
- **Scheduling** - Schedule flows to run automatically using EventBridge
- **AWS Batch** - Run compute-intensive steps as AWS Batch jobs

## Installation

```bash
pip install lokkiflow
```

Or install by uv (recommended):

```bash
uv add lokkiflow
```

## Quick Start

Define a flow with steps:

```python
from lokki import flow, step

@step
def get_birds() -> list[str]:
    return ["goose", "duck", "seagull"]

@step
def flap_bird(bird: str) -> str:
    return f"flappy {bird}"

@step
def join_birds(birds: list[str]) -> str:
    return ", ".join(birds)

@flow
def birds_flow():
    return get_birds().map(flap_bird).agg(join_birds)

if __name__ == "__main__":
    from lokki import main
    main(birds_flow)
```

Run locally:

```bash
python birds_flow.py run
# Output: flappy goose, flappy duck, flappy seagull
```

Build for deployment:

```bash
python birds_flow.py build
```

This creates:
- `lokki-build/lambdas/` - One directory per step with Dockerfile or ZIP
- `lokki-build/statemachine.json` - AWS Step Functions state machine
- `lokki-build/template.yaml` - CloudFormation template

## Configuration

Create a `lokki.toml` in your project:

```toml
# lokki.toml
build_dir = "lokki-build"

[aws]
artifact_bucket = "my-lokki-artifacts"
image_repository = "local"  # or ECR prefix like "123456789.dkr.ecr.us-east-1.amazonaws.com/myproject"
endpoint = ""  # for LocalStack: "http://localhost:4566"

[lambda]
package_type = "image"  # or "zip" for simpler deployments
timeout = 900
memory = 512
image_tag = "latest"

[lambda.env]
LOG_LEVEL = "INFO"

[logging]
level = "INFO"
format = "human"  # or "json"
```

### Configuration Precedence

Environment variables override TOML config (highest to lowest):

| Environment Variable | Config Field |
|---------------------|--------------|
| `LOKKI_ARTIFACT_BUCKET` | `aws.artifact_bucket` |
| `LOKKI_IMAGE_REPOSITORY` | `aws.image_repository` |
| `LOKKI_AWS_ENDPOINT` | `aws.endpoint` |
| `LOKKI_BUILD_DIR` | `build_dir` |
| `LOKKI_LOG_LEVEL` | `logging.level` |

## Flow Syntax

### Basic Example

```python
from lokki import step, flow, main

@step
def get_data():
    return [1, 2, 3]

@step
def process_item(item, mult):
    return item * mult

@step
def process_item_2(item):
    return item * item

@step  
def sum_items(items):
    return sum(items)

@flow
def my_flow(mult=2):
    return get_data().map(process_item, mult=mult).next(process_item_2).agg(sum_items)

if __name__ == "__main__":
    main(my_flow)

```

The example gets item list, maps them through two processing functions and aggregates the result.

### Chaining Methods

- `.map(step)` - Run step in parallel for each item in the list (fan-out)
- `.agg(step)` - Aggregate results from map into a single value (fan-in)
- `.next(step)` - Run step sequentially after the previous step

Chain multiple maps: `step1().map(step2).next(step3).agg(agg_step)`

### Flow Parameters

Pass parameters to flows at runtime:

```python
@step
def fetch_data(limit: int, offset: int = 0):
    return list(range(limit))[offset:]

@step
def process(item, mult):
    return item * mult

@flow
def paginated_flow(limit: int = 100, offset: int = 0, mult: int = 2):
    return fetch_data(limit=limit, offset=offset).map(process, mult=mult)

if __name__ == "__main__":
    main(paginated_flow)
```

Run with parameters:

```bash
python flow.py run --limit 50 --offset 10
```

### Retry Configuration

Configure automatic retries for failed steps:

```python
from lokki import flow, step
from lokki.decorators import RetryConfig

@step
def unreliable_step(data):
    import random
    if random.random() < 0.5:
        raise ValueError("Random failure")
    return data

@flow
def flow_with_retry():
    return unreliable_step(retry=RetryConfig(retries=3, delay=1.0, backoff=2.0))
```

Retry options:
- `retries` - Number of retry attempts (default: 0)
- `delay` - Initial delay between retries in seconds (default: 1.0)
- `backoff` - Backoff multiplier for delay (default: 2.0)

### Scheduling

Schedule flows to run automatically using EventBridge:

```python
from lokki import flow, step

@step
def fetch_data():
    return [1, 2, 3]

@step
def process(item):
    return item * 2

@step
def aggregate(items):
    return sum(items)

# Run daily at 9 AM UTC
@flow(schedule="cron(0 9 * * ? *)")
def daily_pipeline():
    return fetch_data().map(process).agg(aggregate)

# Or run every hour
@flow(schedule="rate(1 hour)")
def hourly_pipeline():
    return fetch_data().process()
```

Schedule expressions:
- **cron** - `cron(minute hour day month day-of-week ?)`
- **rate** - `rate(value unit)` (e.g., `rate(1 hour)`, `rate(30 minutes)`, `rate(1 day)`)

The schedule is deployed as an EventBridge Rule that triggers the Step Functions state machine.

### AWS Batch Support

Run compute-intensive steps as AWS Batch jobs:

```python
from lokki import flow, step

@step(job_type="batch", vcpu=8, memory_mb=16384, timeout_seconds=3600)
def heavy_computation(data):
    # Run as AWS Batch job instead of Lambda
    return process_heavy_data(data)
```

Batch configuration in `lokki.toml`:

```toml
[batch]
job_queue = "my-batch-queue"
job_definition_name = "lokki-batch"
vcpu = 4
memory_mb = 8192
timeout_seconds = 3600
```

## CLI Commands

```bash
python my_flow.py run              # Run locally with optional params
python my_flow.py build            # Build deployment artifacts
python my_flow.py deploy           # Build and deploy to AWS
python my_flow.py show             # Show execution status
python my_flow.py logs             # Fetch CloudWatch logs
python my_flow.py destroy          # Destroy the CloudFormation stack
python my_flow.py --help           # Show help
```

### Run Command

```bash
python flow.py run --param1 value1 --param2 value2
```

### Deploy Command

```bash
python flow.py deploy --stack-name my-stack --region us-east-1
```

### Show Command

```bash
python flow.py show                    # Show last 10 executions
python flow.py show --n 5              # Show last 5 executions
python flow.py show --run <run_id>      # Show specific execution
```

### Logs Command

```bash
python flow.py logs                     # Fetch logs from last hour
python flow.py logs --start 2024-01-15T10:00:00Z
python flow.py logs --tail              # Tail logs in real-time
python flow.py logs --run <run_id>      # Filter by run ID
```

## Deployment

### Option 1: Docker Images (Default)

1. Build your flow:
   ```bash
   python my_flow.py build
   ```

2. Push Lambda images to ECR (from each `lokki-build/lambdas/<step>/` directory):
   ```bash
   docker build -t <ecr-repo>/<step>:<tag> .
   docker push <ecr-repo>/<step>:<tag>
   ```

3. Deploy CloudFormation:
   ```bash
   aws cloudformation deploy \
     --template-file lokki-build/template.yaml \
     --stack-name my-flow \
     --parameter-overrides \
       FlowName=my-flow \
       S3Bucket=my-bucket \
       ImageRepository=123456789.dkr.ecr.us-east-1.amazonaws.com/myproject
   ```

### Option 2: ZIP Archives (Simpler)

For simpler deployments without Docker:

```toml
[lambda]
package_type = "zip"
```

```bash
python my_flow.py deploy
```

The Lambda code will be uploaded directly as ZIP archives - no ECR push needed.

## Local Development with LocalStack

Test your flows locally before deploying to AWS:

1. Start LocalStack:
   ```bash
   cd dev
   docker-compose up -d
   ```

2. Configure for LocalStack:
   ```toml
   [aws]
   artifact_bucket = "lokki"
   endpoint = "http://localhost:4566"
   image_repository = "local"

   [lambda]
   package_type = "zip"
   ```

3. Build and deploy:
   ```bash
   python flow.py build
   python flow.py deploy --confirm
   ```

See `dev/README.md` for more detailed LocalStack testing instructions.

## Architecture

- **@step** - Decorator that marks a function as a pipeline step
- **@flow** - Decorator that wraps a function returning a FlowGraph
- **FlowGraph** - Resolved execution graph with TaskEntry, MapOpenEntry, MapCloseEntry
- **LocalRunner** - Executes flows locally using temporary files
- **Builder** - Generates Lambda packages, state machine, and CloudFormation

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Type check
uv run mypy lokki/

# Lint
uv run ruff check lokki/
```

## License

MIT
