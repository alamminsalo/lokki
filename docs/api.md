# API Reference

This document provides a comprehensive reference for the lokki public API.

---

## Decorators

### `@step`

Decorator that marks a function as a pipeline step. The function will be executed as an AWS Lambda (or Batch job) when deployed.

```python
from lokki import step

@step
def my_step(data):
    return process(data)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fn` | `Callable` | Required | The function to decorate |
| `retry` | `RetryConfig \| dict \| None` | `None` | Retry configuration for transient failures |
| `job_type` | `str` | `"lambda"` | Execution backend: `"lambda"` or `"batch"` |
| `vcpu` | `int \| None` | `None` | Number of vCPUs for Batch jobs (overrides global config) |
| `memory_mb` | `int \| None` | `None` | Memory in MB for Batch jobs (overrides global config) |
| `timeout_seconds` | `int \| None` | `None` | Timeout in seconds for Batch jobs (overrides global config) |

#### Examples

```python
# Basic step
@step
def get_data():
    return [1, 2, 3]

# Step with retry
@step(retry={"retries": 3, "delay": 1, "backoff": 2})
def unreliable_step(data):
    return fetch_data(data)

# Step with Batch configuration
@step(job_type="batch", vcpu=8, memory_mb=16384, timeout_seconds=3600)
def heavy_computation(data):
    return process_heavy(data)
```

---

### `@flow`

Decorator that marks a function as a pipeline flow. The function should return a chain of steps.

```python
from lokki import flow, step

@step
def get_items():
    return [1, 2, 3]

@flow
def my_flow():
    return get_items()
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fn` | `Callable` | Required | The function to decorate |

The flow name is derived from the function name (snake_case → kebab-case).

---

## StepNode Methods

After decorating a function with `@step`, it returns a `StepNode` with the following chaining methods:

### `.map(step_node, concurrency_limit=None, direct_pass=False, **kwargs)`

Starts a Map block for parallel processing. The step runs for each item in the source list.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `step_node` | `StepNode` | Required | The step to run for each item (or list of steps) |
| `concurrency_limit` | `int \| None` | `None` | Maximum parallel iterations (AWS Step Functions MaxConcurrency) |
| `direct_pass` | `bool` | `False` | Pass results in memory between inner steps (reduces S3 API calls) |
| `**kwargs` | `Any` | `{}` | Flow-level parameters passed to the step |

**Returns:** `MapBlock`

**Examples:**

```python
@step
def get_items():
    return [1, 2, 3]

@step
def process_item(item, multiplier):
    return item * multiplier

# Single step in map
get_items().map(process_item, concurrency_limit=10, multiplier=2)

# Multiple steps inside map (list syntax)
get_items().map([process_item, enrich_item], direct_pass=True)
```

---

### `.agg(step_node, **kwargs)`

Closes a Map block and aggregates results from parallel execution. **Optional** — map blocks can end without aggregation.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `step_node` | `StepNode` | Required | Aggregation step that receives list of results |
| `**kwargs` | `Any` | `{}` | Flow-level parameters passed to the step |

**Returns:** `StepNode`

**Example with single step:**

```python
@step
def get_items():
    return [1, 2, 3]

@step
def process(item):
    return item * 2

@step
def aggregate(items):
    return sum(items)

# Single step in map
get_items().map(process).agg(aggregate)
```

**Example with multiple steps (list syntax):**

```python
@step
def get_items():
    return [1, 2, 3]

@step
def transform(item):
    return item * 2

@step
def validate(item):
    return item > 0

@step
def aggregate(items):
    return sum(items)

# Multiple steps inside map - connected sequentially for each item
get_items().map([transform, validate]).agg(aggregate)
```

**Example with direct_pass:**

```python
# direct_pass=True passes results in memory between steps (reduces S3 API calls)
get_items().map([transform, validate], direct_pass=True).agg(aggregate)
```

**Example without aggregation (side-effect only):**

```python
@step
def get_events():
    return [{"id": 1}, {"id": 2}, {"id": 3}]

@step
def send_webhook(event):
    requests.post("https://example.com/webhook", json=event)

get_events().map([send_webhook, log_event], direct_pass=True)

# Without aggregation - each event processed independently
get_events().map(send_webhook)
```

get_items().map(process).agg(aggregate)
```

---

## MapBlock Methods

A `MapBlock` is returned by `.map()`. It supports chaining steps inside the map block. The `.agg()` method is **optional** — the map can end without aggregation for side-effect-only processing.

### `.map(step_node, concurrency_limit=None, **kwargs)`

Add another step to the inner chain (inside the Map block).

**Example:**

```python
source.map(step1).map(step2).agg(aggregate)
```

---

### `.next(step_node, **kwargs)`

Add a step to the inner chain (shorthand for `.map()`).

**Example:**

```python
source.map(step1).next(step2).agg(aggregate)
```

Or without aggregation:

```python
# Event sending pipeline - each step processes independently
source.map(send_event)  # No .agg() needed
```

---

### `.agg(step_node, **kwargs)`

Close the Map block and attach an aggregation step.

**Example:**

```python
source.map(process).agg(aggregate)
```

---

## RetryConfig

Dataclass for configuring retry behavior on steps.

```python
from lokki.decorators import RetryConfig

RetryConfig(retries=3, delay=1.0, backoff=2.0, max_delay=60.0, exceptions=(Exception,))
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `retries` | `int` | `0` | Maximum number of retry attempts |
| `delay` | `float` | `1.0` | Initial delay between retries in seconds |
| `backoff` | `float` | `2.0` | Multiplier applied to delay after each retry |
| `max_delay` | `float` | `60.0` | Maximum delay cap in seconds |
| `exceptions` | `tuple[type, ...]` | `(Exception,)` | Tuple of exception types to catch |

---

## CLI Commands

### `run`

Execute the flow locally.

```bash
python flow.py run [--param1 value1] [--param2 value2]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--param` | Flow parameters (passed to the flow function) |

---

### `build`

Generate deployment artifacts.

```bash
python flow.py build [--param1 value1] [--param2 value2]
```

Creates:
- `lokki-build/lambdas/` - Lambda packages (Dockerfiles or ZIPs)
- `lokki-build/statemachine.json` - AWS Step Functions state machine
- `lokki-build/template.yaml` - CloudFormation template

---

### `deploy`

Build and deploy to AWS.

```bash
python flow.py deploy --stack-name <name> --region <region> [--image-tag <tag>] [--confirm]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--stack-name` | CloudFormation stack name |
| `--region` | AWS region (default: us-east-1) |
| `--image-tag` | Docker image tag (default: latest) |
| `--confirm` | Skip confirmation prompt |

---

### `invoke`

Invoke the deployed flow on AWS via Step Functions.

```bash
python flow.py invoke [--param1 value1] [--param2 value2]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--param` | Flow parameters (passed to the deployed flow) |

---

### `show`

Show execution status.

```bash
python flow.py show [--n <count>] [--run <run_id>]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--n` | Number of executions to show (default: 10) |
| `--run` | Specific run ID to show |

---

### `logs`

Fetch CloudWatch logs.

```bash
python flow.py logs [--start <datetime>] [--end <datetime>] [--run <run_id>] [--tail]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--start` | Start time (ISO 8601 format, default: 1 hour ago) |
| `--end` | End time (ISO 8601 format, default: now) |
| `--run` | Filter by specific run ID |
| `--tail` | Continuously poll logs |

---

### `destroy`

Delete the CloudFormation stack.

```bash
python flow.py destroy [--confirm]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--confirm` | Skip confirmation prompt |

---

## Configuration

Create a `lokki.toml` file in your project root.
See [docs/config.md](./config.md)

### Environment Variables

Environment variables override TOML configuration:

| Variable | Config Field |
|----------|--------------|
| `LOKKI_ARTIFACT_BUCKET` | `aws.artifact_bucket` |
| `LOKKI_IMAGE_REPOSITORY` | `aws.image_repository` |
| `LOKKI_AWS_ENDPOINT` | `aws.endpoint` |
| `LOKKI_BUILD_DIR` | `build_dir` |
| `LOKKI_LOG_LEVEL` | `logging.level` |
| `LOKKI_BATCH_JOB_QUEUE` | `batch.job_queue` |
| `LOKKI_BATCH_JOB_DEFINITION` | `batch.job_definition_name` |

---

## Public Functions

### `main(flow_fn)`

Entry point for CLI commands. Add to your script's `__main__` block.

```python
from lokki import flow, step, main

@flow
def my_flow():
    ...

if __name__ == "__main__":
    main(my_flow)
```

---

### `load_config()` (internal)

Loads configuration from `~/.lokki/lokki.toml` and `./lokki.toml`, merges them, and applies environment variable overrides.

**Returns:** `LokkiConfig`

---

## Flow-Level Parameters

Flow-level parameters allow passing constants to steps without threading them through the pipeline:

```python
@step
def process(item, multiplier=1):
    return item * multiplier

@flow
def my_flow():
    return get_items().map(process, multiplier=10)
```

The `multiplier=10` is available in `process` as a keyword argument, independent of the pipeline data flow.

---

## Complete Example

```python
from lokki import flow, step, main
from lokki.decorators import RetryConfig

@step
def generate_route_date_pairs(route, start_date, end_date):
    """Generate all route/date combinations."""
    routes = [
        dict(origin=route[0], destination=route[1]),
        dict(origin=route[1], destination=route[0]),
    ]
    # Generate date list...
    return [(r["origin"], r["destination"], d) for r in routes for d in dates]

@step(retry=RetryConfig(retries=2, delay=1, backoff=2))
def fetch_flights(route_tuple):
    """Fetch flights for a specific route and date."""
    origin, destination, date = route_tuple
    # Fetch flights...
    return df

@step
def collect_dataframes(dfs):
    """Aggregate flight data from all routes."""
    return duckdb.sql("SELECT ...").df()

@flow
def flight_pipeline(origin, destination, begin_date, days):
    """Main flight data pipeline."""
    end_date = calculate_end_date(begin_date, days)
    
    return (
        generate_route_date_pairs((origin, destination), begin_date, end_date)
        .map(fetch_flights, concurrency_limit=20)
        .agg(collect_dataframes)
    )

if __name__ == "__main__":
    main(flight_pipeline)
```
