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

### Simple Chaining with `.next()`

In addition to `.map()` and `.agg()`, steps can be chained sequentially using `.next()`:

```python
@step
def get_data() -> list[int]:
    return [1, 2, 3]

@step
def process(items: list[int]) -> int:
    return sum([item * 2 for item in items])

@step
def save(result: int) -> str:
    return f"Result: {result}"

@flow
def linear_flow():
    # Simple sequential chain: A → B → C
    return get_data().next(process).next(save)
```

**Behavior:**
- `.next(step)` chains a step after the current one without parallelism
- The output of the previous step becomes the input to the next step
- This is equivalent to a simple linear pipeline without map/aggregation
- Multiple `.next()` calls create a linear chain: `A.next(B).next(C)` → A → B → C
- Calling `.next(step)` after `.map(step)` continues the chain inside the mapped section until `.agg(step)` is called:

```python
@step
def get_data() -> list[int]:
    return [1, 2, 3]

@step
def mult_item(item: int) -> int:
    return item * 2

@step
def pow_item(item: int) -> int:
    return item ** item

@step
def collect(result: list[int]) -> str:
    sum = sum(result)
    return f"Sum: {sum}"

@flow
def complex_flow():
    # Chain A -> Map(B -> C) -> Agg(D)
    return get_data().map(mult_item).next(pow_item).agg(collect)
```
- The flow must raise an exception if the flow ends with an open Map block.
- Nested .map() calls is not supported and should raise an exception.


**Comparison:**

| Method | Input | Output | Use Case |
|--------|-------|--------|------------|
| `.map(step)` | list | list (per-item) | Parallel processing |
| `.agg(step)` | list | single value | Aggregation |
| `.next(step)` | any | any | Sequential/linear chain |

---

## CLI Interface

The flow script is the entry point for all lokki operations.

| Command | Description |
|---|---|
| `python flow_script.py build` | Package and generate all deployment artifacts |
| `python flow_script.py run` | Execute the pipeline locally |
| `python flow_script.py deploy` | Build and deploy to AWS Step Functions |

---

## Deploy Command

The `deploy` command builds the flow and deploys it to AWS Step Functions. It performs the following steps:

1. **Build** - Runs the same build process as `build` command
2. **Push Lambda Images** - Builds and pushes Docker images to ECR for each step
3. **Deploy CloudFormation** - Creates or updates the CloudFormation stack

### Prerequisites

- AWS credentials configured (via `aws configure` or environment variables)
- ECR repository exists (created manually or as part of a previous deployment)
- S3 bucket for intermediate data exists

### Usage

```bash
python flow_script.py deploy
```

### Options

| Option | Description |
|--------|-------------|
| `--stack-name NAME` | CloudFormation stack name (default: derived from flow name) |
| `--region REGION` | AWS region (default: from AWS config) |
| `--image-tag TAG` | Docker image tag (default: latest) |
| `--confirm` | Skip confirmation prompt |

### Configuration

The deploy command uses the same configuration as `build`:

```yaml
# lokki.yml
artifact_bucket: my-lokki-artifacts
ecr_repo_prefix: 123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject
```

### Deploy Workflow

1. **Validate** - Check AWS credentials and required configuration
2. **Build** - Generate Lambda packages, state machine, CloudFormation template
3. **Build & Push Images** - For each step:
   - Build Docker image from `lokki-build/lambdas/<step>/`
   - Push to ECR: `<ecr_repo_prefix>/<step>:<image-tag>`
4. **Deploy Stack** - Run `aws cloudformation deploy`:
   ```bash
   aws cloudformation deploy \
     --template-file lokki-build/template.yaml \
     --stack-name <stack-name> \
     --capabilities CAPABILITY_IAM \
     --parameter-overrides \
       FlowName=<flow-name> \
       S3Bucket=<artifact-bucket> \
       ECRRepoPrefix=<ecr-repo-prefix> \
       ImageTag=<image-tag>
   ```
5. **Report** - Display stack status and output

### Output

On success:
```
✓ Built Lambda packages
✓ Pushed 3 images to ECR
✓ Deployed CloudFormation stack 'my-flow'
  State Machine ARN: arn:aws:states:eu-west-1:123456789:stateMachine:my-flow
```

On failure:
```
✗ Build failed: <error>
```
or
```
✗ Deploy failed: <CloudFormation error>
```

### Continuous Deployment

For CI/CD pipelines, use `--confirm` to skip prompts:

```bash
python flow_script.py deploy --confirm --image-tag $VERSION
```

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

## Logging & Observability

### Overview

The lokki library provides structured logging to help developers track pipeline execution. Logging is designed to be human-readable by default (suitable for development/CLI use) with optional structured JSON output for production environments.

### Log Levels

| Level | When Used |
|-------|-----------|
| `DEBUG` | Detailed execution information (disabled by default) |
| `INFO` | Step start/completion, map progress updates |
| `WARNING` | Non-fatal issues (e.g., retry warnings) |
| `ERROR` | Step failures, exceptions |

The default log level is `INFO`. It can be configured via:
- Environment variable: `LOKKI_LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR)
- Config file: `lokki.yml` under `logging.level`

### Step Execution Logging

For each step, lokki logs:

1. **Step Start**
   ```
   [INFO] Step 'step_name' started at 2024-01-15T10:30:00
   ```

2. **Step Completion**
   ```
   [INFO] Step 'step_name' completed in 2.345s (status=success)
   ```
   
   Or on failure:
   ```
   [ERROR] Step 'step_name' failed after 1.234s: ValueError: invalid input
   ```

### Map Task Progress

For `.map()` blocks, detailed progress is logged showing individual item status:

```
[INFO] Map 'process_items' started (100 items)
[INFO]   [=====>                    ] 30/100 (30%) completed
[INFO]   [=============>             ] 60/100 (60%) completed
[INFO]   [=========================>] 100/100 (100%) completed
[INFO] Map 'process_items' completed in 4.567s
```

Individual item statuses:
- `pending` — queued for execution
- `running` — currently being processed
- `completed` — finished successfully
- `failed` — raised an exception

Progress updates occur at configurable intervals (default: every 10% or every 10 items, whichever is more frequent).

### Configuration Options

```yaml
# lokki.yml
logging:
  level: INFO              # DEBUG, INFO, WARNING, ERROR
  format: human           # "human" (default) or "json"
  progress_interval: 10    # Update every N items or 10% (whichever is smaller)
  show_timestamps: true   # Include ISO timestamps in log output
```

### JSON Structured Logging

When `format: json` is set, each log line is a JSON object:

```json
{"level": "INFO", "ts": "2024-01-15T10:30:00.123Z", "event": "step_start", "step": "get_data", "run_id": "abc123"}
{"level": "INFO", "ts": "2024-01-15T10:30:02.456Z", "event": "step_complete", "step": "get_data", "duration": 2.333, "status": "success"}
{"level": "INFO", "ts": "2024-01-15T10:30:02.789Z", "event": "map_progress", "step": "process", "total": 100, "completed": 50, "failed": 0}
```

### Runtime Handler Logging

In AWS Lambda, logs are emitted to CloudWatch. The handler logs:
- Function invocation (cold start, warm)
- Input URL processing
- Step execution duration
- Output upload confirmation
- Any errors with stack traces

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

# AWS configuration
aws:
  # S3 bucket for intermediate pipeline data and build artifacts
  artifact_bucket: my-lokki-artifacts
  
  # ECR repository prefix for Lambda container images
  # Leave empty to use local Docker images (e.g., for LocalStack testing)
  # Example: 123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject
  ecr_repo_prefix: ""
  
  # AWS endpoint URL for local development (e.g., LocalStack)
  # Leave empty to use real AWS endpoints
  # Example: http://localhost:4566
  endpoint: ""
  
  # IAM role ARNs
  roles:
    pipeline: arn:aws:iam::123456789::role/lokki-stepfunctions-role
    lambda: arn:aws:iam::123456789::role/lokki-lambda-execution-role

# Lambda configuration
lambda:
  # Deployment package type: "image" (default) or "zip"
  # - image: Docker container image pushed to ECR
  # - zip: ZIP archive uploaded directly to Lambda
  # Use "zip" for LocalStack testing or simpler deployments
  package_type: image
  
  # Default Lambda resource configuration
  timeout: 900          # seconds
  memory: 512           # MB
  image_tag: latest
  
  # Environment variables injected into every Lambda function
  env:
    LOG_LEVEL: INFO
    MY_API_ENDPOINT: https://api.example.com

# Output directory for build artifacts (default: lokki-build)
build_dir: lokki-build

# Logging configuration
logging:
  level: INFO           # DEBUG, INFO, WARNING, ERROR
  format: human        # "human" or "json"
  progress_interval: 10  # Update every N items or 10% (whichever is smaller)
  show_timestamps: true # Include ISO timestamps in log output
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

## Lambda Deployment Modes

lokki supports two Lambda deployment modes: **container image** and **ZIP archive**.

### Container Image (Default)

Each `@step` function is packaged into its own Docker container image pushed to ECR. This is the default and recommended approach for production deployments.

**Advantages:**
- Full control over runtime environment
- Larger deployment package size (10GB limit vs 50MB for ZIP)
- Better for dependencies with native extensions

**Requirements:**
- ECR repository for storing images
- Docker installed and configured

### ZIP Archive

Each `@step` function is packaged as a ZIP archive uploaded directly to Lambda. This mode is useful for:

- **LocalStack testing** — LocalStack has limited support for container image-based Lambdas
- **Simpler deployments** — No need for ECR or Docker
- **Smaller packages** — When step functions have minimal dependencies

**Advantages:**
- No Docker or ECR required
- Faster builds (no image push/pull)
- Simpler CI/CD pipelines

**Limitations:**
- 50MB deployment package size (250MB unzipped)
- Not suitable for dependencies with large native extensions

### Configuration

To enable ZIP deployment mode, set `package_type: zip` in `lokki.yml`:

```yaml
# lokki.yml
lambda:
  package_type: zip  # "image" (default) or "zip"
  timeout: 900
  memory: 512
```

When `package_type: zip` is set:
- The build process generates a ZIP file per step instead of a Dockerfile
- The CloudFormation template uses `PackageType: ZipFile` instead of `PackageType: Image`
- No Docker build or ECR push is performed during deployment
- The Lambda runtime automatically installs dependencies from `requirements.txt` generated at build time

---

## Non-Functional Requirements

- **Single deployment target**: AWS Step Functions (no other cloud providers in scope).
- **Parallelism**: Map states must support very large fan-out (thousands of items) via the Distributed Map pattern reading from S3.
- **Minimal boilerplate**: Users write plain Python functions; all AWS plumbing is invisible.
- **Reproducibility**: Build artifacts are deterministic given the same source and dependency lock file.
- **Extensibility**: The decorator and chaining API should not preclude adding further deployment targets or step types in future.

---

## Local Testing with LocalStack

### Purpose

Local testing with LocalStack and SAM CLI provides an environment that **simulates real AWS** locally, enabling developers to test their pipelines without incurring AWS costs or requiring internet connectivity. This significantly improves code quality by catching deployment and integration issues early in the development cycle.

### Benefits

1. **AWS Simulation**: LocalStack provides local implementations of AWS services (S3, Lambda, Step Functions, CloudFormation, ECR)
2. **Fast Iteration**: No need to deploy to real AWS for testing
3. **Cost Free**: No AWS charges for local development
4. **Offline Development**: Works without internet connectivity
5. **Full Pipeline Testing**: Can test the complete flow including Step Functions orchestration

### Components

| Component | Role |
|-----------|------|
| **LocalStack** | Local AWS cloud stack (S3, Lambda, Step Functions, CloudFormation) |
| **SAM CLI** | Local Lambda invocation and deployment |
| **ZIP Deployment** | Package type for Lambda functions (required for LocalStack) |

### Configuration

For local testing, configure `lokki.yml`:

```yaml
# lokki.yml
aws:
  endpoint: http://localhost:4566
  artifact_bucket: lokki

lambda:
  package_type: zip  # Required for LocalStack
```

### Workflow

| Step | Command | Description |
|------|---------|-------------|
| Start LocalStack | `localstack start -d` | Start LocalStack services |
| Build | `python flow_script.py build` | Generate deployment artifacts |
| Deploy | `python flow_script.py deploy` | Deploy to LocalStack |
| Test Lambda | `sam local invoke GetBirdsFunction` | Test individual functions |
| Test Pipeline | `aws stepfunctions start-execution ...` | Run full pipeline |
| Verify S3 | `aws s3 ls s3://lokki/` | Check outputs |

### Testing Individual Steps

```bash
# Build first
python flow_script.py build

# Invoke a specific Lambda function locally
cd lokki-build
sam local invoke GetBirdsFunction --template sam.yaml

# Or start local Lambda endpoint
sam local start-lambda --template sam.yaml --port 3001
```

### Verifying Pipeline Execution

```bash
# Check S3 for outputs
aws --endpoint-url=http://localhost:4566 s3 ls s3://lokki/

# Download and inspect output
aws --endpoint-url=http://localhost:4566 s3 cp s3://lokki/.../output.pkl.gz -
```

### Limitations

- LocalStack does not support all AWS service features
- Some AWS Lambda features may behave differently
- Container image-based Lambda not fully supported (use ZIP deployment)
- Step Functions local has limited state machine size

---

## Out of Scope (v1)

- Non-AWS deployment targets
- Conditional branching / dynamic routing between steps
- Step retries and error handling configuration (beyond Step Functions defaults)
- Streaming or incremental step outputs
- Web UI or dashboard
