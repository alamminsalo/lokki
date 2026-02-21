# lokki

[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue)](https://pypi.org/project/lokki/)
[![Test Coverage](https://img.shields.io/badge/coverage-77%25-yellow)](https://github.com/anomalyco/lokki/actions)
[![Tests](https://img.shields.io/badge/tests-152%20passed-green)](https://github.com/anomalyco/lokki/actions)

A Python library for defining, building, and deploying data pipelines to AWS Step Functions.

## Features

- **Simple Python decorators** - Define pipelines using `@step` and `@flow` decorators
- **Local execution** - Test your flows locally before deploying
- **AWS Step Functions** - Deploy to AWS Step Functions with Distributed Map for parallel processing
- **Lambda packaging** - Auto-generates Docker images for each step
- **CloudFormation** - Generates complete CloudFormation templates for deployment

## Installation

```bash
pip install lokki
```

Or install from source:

```bash
uv sync
```

## Quick Start

Define a flow with steps:

```python
from lokki import flow, step

@step
def get_birds() -> list[str]:
    return ["goose", "duck", "seagul"]

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
# Output: flappy goose, flappy duck, flappy seagul
```

Build for deployment:

```bash
python birds_flow.py build
```

This creates:
- `lokki-build/lambdas/` - One directory per step with Dockerfile and handler
- `lokki-build/statemachine.json` - AWS Step Functions state machine
- `lokki-build/template.yaml` - CloudFormation template

## Configuration

Create a `lokki.yml` in your project:

```yaml
artifact_bucket: my-lokki-artifacts
ecr_repo_prefix: 123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject
build_dir: lokki-build

lambda_defaults:
  timeout: 900
  memory: 512
  image_tag: latest

lambda_env:
  LOG_LEVEL: INFO
```

### Configuration Precedence

Environment variables override YAML config:

| Environment Variable | Config Field |
|---------------------|--------------|
| `LOKKI_ARTIFACT_BUCKET` | `artifact_bucket` |
| `LOKKI_ECR_REPO_PREFIX` | `ecr_repo_prefix` |
| `LOKKI_BUILD_DIR` | `build_dir` |

## Flow Syntax

### Basic Steps

```python
@step
def get_data():
    return [1, 2, 3]

@step
def process(item):
    return item * 2

@step  
def summarize(items):
    return sum(items)

@flow
def my_flow():
    return get_data().map(process).agg(summarize)
```

### Chaining

- `.map(step)` - Run step in parallel for each item in the list
- `.agg(step)` - Aggregate results from map into a single value
- Chain multiple maps: `step1().map(step2).map(step3).agg(agg_step)`

## CLI Commands

```bash
python my_flow.py run     # Run locally
python my_flow.py build   # Build deployment artifacts
python my_flow.py --help  # Show help
```

## Deployment

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
       ECRRepoPrefix=123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject
   ```

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
