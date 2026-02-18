# lokki — Requirements Specification

## Overview

**lokki** is a Python library for defining, building, and running data pipelines using simple function decorators. Pipelines are expressed as pure Python code and deployed to AWS Step Functions, with S3 used transparently for inter-step data passing.

---

## Core Concepts

### `@step` Decorator

- Marks a regular Python function as a pipeline step.
- Each step is independently packaged and executed (as an AWS Lambda function).
- **S3 abstraction**: inputs and outputs are automatically serialised to/from S3. Functions are authored as if they receive and return plain Python objects; lokki handles all S3 URL resolution transparently.
- Decorated steps expose two chaining methods:
  - `.map(step_fn)` — fan-out: runs the next step in parallel once per item in the current step's output (list). Starts a Map block in the state machine.
  - `.agg(step_fn)` — fan-in: collects all parallel outputs into a list and passes it to the next step as a single input. Ends the current Map block.
- Steps can be chained: `step_a().map(step_b).agg(step_c)`.

### `@flow` Decorator

- Marks a function as the pipeline entry point.
- The body of the flow function is executed at **build time** (and during local runs) to construct the execution graph by calling and chaining `@step`-decorated functions.
- The flow function may set default arguments for the first step. These defaults can be overridden at runtime by passing a JSON input dictionary to the deployed Step Functions state machine.
- A flow function must return a chained step expression.

**Example:**

```python
# birds_flow_example.py
from lokki import flow, step

@step
def get_birds():
    return ["goose", "duck", "seagul"]

@step
def flap_bird(bird):
    return f"flappy {bird}"

@step
def join_birds(birds):
    return ", ".join(birds)

@flow
def birds_flow():
    return get_birds().map(flap_bird).agg(join_birds)
```

---

## CLI Interface

The flow script is the entry point for all lokki operations.

| Command | Description |
|---|---|
| `python flow_script.py build` | Package and generate all deployment artifacts |
| `python flow_script.py run` | Execute the pipeline locally |

---

## Build Artifacts

Running `python flow_script.py build` produces the following outputs:

### 1. Lambda Dockerfile Directories (one per `@step`)

- Each `@step` function is packaged into its own directory containing a `Dockerfile`.
- The Dockerfile uses the official AWS Lambda Python base images:
  - Build stage: `public.ecr.aws/lambda/python:latest` (or pinned version)
  - Runtime stage: same image as the runtime
- Dependencies are sourced from the project's `pyproject.toml` and pinned via `uv.lock`. At build time, lokki reads these files and installs the resolved dependency set into each Lambda image using `uv`.
- The lokki library itself is included in each image via a symlink into the Lambda package directory rather than copying, avoiding duplication across step images.
- The uv package manager handles all dependency installation inside images.

### 2. Step Functions State Machine JSON

- Models the full pipeline as an AWS Step Functions state machine definition.
- Sequential steps map to a `Task` state chain.
- `.map()` opens a `Map` state using the **Distributed Map** (or `ItemReader` from S3) pattern, enabling very high parallelism. The map state reads its input item list from a JSON file stored in S3.
- `.agg()` closes the Map block; subsequent steps resume in the outer sequence.
- Nested `.map().agg()` blocks are supported.
- Inter-step data is passed via S3 URLs embedded in the state machine I/O; step functions do not pass large payloads directly.

### 3. CloudFormation YAML Template

- Deployable template covering:
  - IAM roles and policies for Lambda execution and Step Functions orchestration
  - Lambda function resources (one per `@step`), referencing the built container images from ECR
  - Step Functions state machine resource
  - S3 bucket (or reference to existing bucket) for intermediate data storage
- Parameterised to allow environment-specific overrides (e.g. S3 bucket name, ECR repo prefix).

---

## Local Run

Running `python flow_script.py run` executes the full pipeline locally:

- Steps are run as regular Python functions in-process (no Lambda or S3 required).
- S3 abstraction is replaced with a local temporary directory or in-memory store for intermediate outputs.
- The flow function body is called directly to resolve the execution graph, then steps are executed in dependency order, respecting `.map()` fan-out (using `concurrent.futures` or sequential iteration) and `.agg()` fan-in.
- Useful for fast iteration and debugging without AWS credentials.

---

## Data & S3 Abstraction

- All inter-step data is serialised using **gzip-compressed pickle** and stored in S3 under a structured key prefix (e.g. `s3://<bucket>/lokki/<run_id>/<step_name>/output.pkl.gz`).
- Step functions receive Python objects, not S3 URLs — lokki's runtime wrapper handles download before invocation and upload after return.
- The S3 bucket and prefix are configurable via `lokki.yml` or environment variable override.

---

## Configuration — `lokki.yml`

lokki is configured via a YAML file named `lokki.yml`. Two locations are supported, loaded in order with the local file taking precedence over the global file on a per-field basis:

- **Global**: `~/.lokki/lokki.yml` — user-level defaults shared across all projects.
- **Local**: `lokki.yml` in the project root — project-specific settings that override any matching global field.

Neither file is required; lokki falls back to sensible defaults or environment variables where possible.

**Supported fields:**

```yaml
# lokki.yml

# S3 bucket used for intermediate pipeline data and build artifacts
artifact_bucket: my-lokki-artifacts

# IAM role ARNs
roles:
  pipeline: arn:aws:iam::123456789::role/lokki-stepfunctions-role
  lambda: arn:aws:iam::123456789::role/lokki-lambda-execution-role

# Environment variables injected into every Lambda function
lambda_env:
  LOG_LEVEL: INFO
  MY_API_ENDPOINT: https://api.example.com

# ECR repository prefix for Lambda container images
ecr_repo_prefix: 123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject

# Output directory for build artifacts (default: lokki-build)
build_dir: lokki-build

# Default Lambda resource configuration
lambda_defaults:
  timeout: 900          # seconds
  memory: 512           # MB
  image_tag: latest
```

**Merge behaviour**: when both files are present, they are deep-merged. Any field present in the local `lokki.yml` overrides the corresponding field in the global file. Fields absent from the local file inherit the global value. List values (e.g. under `lambda_env`) are replaced entirely by the local file, not concatenated.

**Resolution order** (highest to lowest precedence): environment variables → local `lokki.yml` → global `~/.lokki/lokki.yml` → built-in defaults.

The **flow name** is not a configurable field — it is always derived from the `@flow`-decorated function name at build time (e.g. `birds_flow` → `"birds-flow"`). It is used as the identifier in CloudFormation resource names, S3 key prefixes, and the Step Functions state machine name.

---

## Dependencies

| Dependency | Role |
|---|---|
| `uv` | Dependency management and virtual environment tooling |
| `stepfunctions` (pip) | AWS Step Functions SDK / state machine construction helpers |
| `boto3` | AWS SDK for S3 and Step Functions API calls |
| `pyyaml` | Parsing `lokki.yml` configuration files |

---

## Non-Functional Requirements

- **Single deployment target**: AWS Step Functions (no other cloud providers in scope).
- **Parallelism**: Map states must support very large fan-out (thousands of items) via the Distributed Map pattern reading from S3.
- **Minimal boilerplate**: Users write plain Python functions; all AWS plumbing is invisible.
- **Reproducibility**: Build artifacts are deterministic given the same source and dependency lock file.
- **Extensibility**: The decorator and chaining API should not preclude adding further deployment targets or step types in future.

---

## Out of Scope (v1)

- Non-AWS deployment targets
- Conditional branching / dynamic routing between steps
- Step retries and error handling configuration (beyond Step Functions defaults)
- Streaming or incremental step outputs
- Web UI or dashboard
