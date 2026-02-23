# lokki — Design Document

## Table of Contents

1. [Repository Layout](#1-repository-layout)
2. [Library Architecture](#2-library-architecture)
3. [Decorator Design](#3-decorator-design)
4. [Execution Graph](#4-execution-graph)
5. [CLI Entry Point](#5-cli-entry-point)
6. [Local Runner](#6-local-runner)
7. [Build Pipeline](#7-build-pipeline)
8. [S3 \& Serialisation Layer](#8-s3--serialisation-layer)
9. [State Machine Generation](#9-state-machine-generation)
10. [CloudFormation Template Generation](#10-cloudformation-template-generation)
11. [Lambda Packaging](#11-lambda-packaging)
12. [Runtime Wrapper (Lambda Handler)](#12-runtime-wrapper-lambda-handler)
13. [Configuration](#13-configuration)
14. [Data Flow Walkthrough](#14-data-flow-walkthrough)
15. [Logging \& Observability](#15-logging--observability)
16. [Deploy Command](#16-deploy-command)
17. [AWS Batch Support](#17-aws-batch-support)

---

## 1. Repository Layout

```
lokki/
├── lokki/
│   ├── __init__.py              # Public API: exports flow, step
│   ├── decorators.py            # @step and @flow decorator implementations
│   ├── graph.py                 # StepNode, FlowGraph — execution graph model
│   ├── runner.py                # Local execution engine
│   ├── builder/
│   │   ├── __init__.py
│   │   ├── builder.py           # Orchestrates the full build
│   │   ├── lambda_pkg.py        # Generates per-step Dockerfile directories
│   │   ├── state_machine.py     # Generates Step Functions JSON
│   │   └── cloudformation.py   # Generates CloudFormation YAML
│   ├── runtime/
│   │   ├── __init__.py
│   │   └── handler.py           # Lambda handler wrapper (runs inside Lambda)
│   ├── s3.py                    # S3 read/write with gzip pickle
│   └── config.py                # Configuration loading
├── pyproject.toml
├── uv.lock
└── README.md
```

The `lokki/runtime/` subpackage is the only code that runs inside deployed Lambda functions. The `lokki/builder/` subpackage runs only at build time on the developer's machine.

---

## 2. Library Architecture

```
┌─────────────────────────────────────────────┐
│                User flow script              │
│   @step / @flow decorators, chaining API    │
└────────────────┬────────────────────────────┘
                 │ builds
                 ▼
┌─────────────────────────────────────────────┐
│              FlowGraph                       │
│   Ordered list of StepNode / MapBlock       │
└────┬─────────────────────┬──────────────────┘
     │                     │
     ▼                     ▼
┌──────────┐        ┌─────────────────────────┐
│  runner  │        │        builder           │
│ (local)  │        │  lambda_pkg              │
└──────────┘        │  state_machine           │
                    │  cloudformation          │
                    └─────────────────────────┘
```

---

## 3. Decorator Design

### `@step`

`step` is implemented as a decorator that wraps the user's function in a `StepNode` object. When called at flow-definition time, it does **not** execute the function — it records it in the graph and returns itself to allow chaining.

```python
# decorators.py (simplified)

@dataclass
class RetryConfig:
    retries: int = 0
    delay: float = 1.0
    backoff: float = 1.0
    max_delay: float = 60.0
    exceptions: tuple[type, ...] = (Exception,)

class StepNode:
    def __init__(self, fn, retry: RetryConfig | None = None):
        self.fn = fn
        self.name = fn.__name__
        self.retry = retry or RetryConfig()
        self._next: StepNode | None = None
        self._map_block: MapBlock | None = None

    def __call__(self, *args, **kwargs):
        # Called inside @flow body — registers default args, returns self for chaining
        self._default_args = args
        self._default_kwargs = kwargs
        return self

    def map(self, step_node: "StepNode") -> "MapBlock":
        block = MapBlock(source=self, inner_head=step_node)
        self._map_block = block
        return block

    def agg(self, step_node: "StepNode") -> "StepNode":
        # Should be called on a MapBlock, not directly on StepNode
        raise TypeError(".agg() must be called on the result of .map()")


class MapBlock:
    """Represents an open fan-out block started by .map()."""
    def __init__(self, source: StepNode, inner_head: StepNode):
        self.source = source          # step before the Map
        self.inner_head = inner_head  # first step inside Map iterator
        self.inner_tail = inner_head  # last step inside Map iterator (grows with chaining)
        self._next: StepNode | None = None

    def map(self, step_node: StepNode) -> "MapBlock":
        # Further chaining inside the Map block
        self.inner_tail._next = step_node
        self.inner_tail = step_node
        return self

    def agg(self, step_node: StepNode) -> StepNode:
        # Closes the Map block, attaches aggregation step after
        step_node._closes_map_block = self
        self._next = step_node
        return step_node


def step(fn, retry: RetryConfig | None = None):
    node = StepNode(fn, retry=retry)
    return node
```

### Retry Configuration

Each step can optionally specify a retry policy via the `retry` parameter:

```python
@step(retry={"retries": 3, "delay": 2, "backoff": 2})
def fetch_data(url: str) -> dict:
    return requests.get(url).json()
```

**RetryConfig fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `retries` | `int` | 0 | Maximum retry attempts |
| `delay` | `float` | 1.0 | Initial delay in seconds |
| `backoff` | `float` | 1.0 | Exponential backoff multiplier |
| `max_delay` | `float` | 60.0 | Maximum delay cap |
| `exceptions` | `tuple[type]` | `(Exception,)` | Exception types to retry |

### `@flow`

`flow` wraps the user's function so that calling it returns a `FlowGraph` — a resolved execution graph — rather than executing the pipeline.

```python
class FlowGraph:
    def __init__(self, name: str, head: StepNode | MapBlock):
        self.name = name
        self.head = head
        self.nodes: list[StepNode] = []   # topological order, populated on resolve()
        self._resolve(head)

    def _resolve(self, node):
        # Walk the chain and collect all StepNodes in order
        ...

def flow(fn):
    def wrapper(*args, **kwargs):
        head = fn(*args, **kwargs)
        return FlowGraph(name=fn.__name__, head=head)
    wrapper._is_flow = True
    wrapper._fn = fn
    return wrapper
```

### Chaining semantics

`.map(b)` always returns a `MapBlock`, not a `StepNode`. `.agg(c)` closes the `MapBlock` and returns a `StepNode` (the aggregation step), allowing further chaining after the fan-in. This means the chain `a().map(b).agg(c).map(d).agg(e)` is valid and produces nested Map blocks.

### `.next()` method for linear chaining

In addition to `.map()` and `.agg()`, steps can be chained sequentially using `.next()`:

```python
@step
def get_data():
    return [1, 2, 3]

@step
def process(items):
    return sum(item * 2 for item in items)

@step
def save(result):
    return f"Result: {result}"

@flow
def linear_flow():
    return get_data().next(process).next(save)
```

**Behavior:**
- `.next(step)` chains a step after the current one without parallelism
- Returns the next `StepNode` to allow further chaining
- Multiple `.next()` calls create a linear chain: `A.next(B).next(C)` → A → B → C

**Chaining after `.map()`:**
Calling `.next(step)` after `.map(step)` continues the chain inside the mapped section:

```python
@flow
def complex_flow():
    # Chain A -> Map(B -> C) -> Agg(D)
    return get_data().map(mult_item).next(pow_item).agg(collect)
```

The `.next()` method is implemented on both `StepNode` and `MapBlock`:
- On `StepNode`: chains to the next step directly
- On `MapBlock`: adds the step to the inner chain (before `.agg()`)

### Flow-level parameters with `.next()`

The `.next()` method supports passing flow-level parameters directly to steps, avoiding the need to thread parameters through intermediate steps:

```python
@step
def get_data():
    return [1, 2, 3]

@step
def process_multiplied(items, multiplier):
    return [item * multiplier for item in items]

@step
def save(result):
    return f"Result: {result}"

@flow
def flow_with_params(multiplier=2):
    # Flow input 'multiplier' is passed directly to process_multiplied
    return get_data().next(process_multiplied, multiplier=multiplier).next(save)
```

**Behavior:**
- `.next(step, **flow_kwargs)` accepts keyword arguments that are injected into the step
- The step function receives:
  - **First positional argument**: previous step's output (passed automatically)
  - **Keyword arguments**: flow-level parameters from `.next()` call

**Parameter resolution:**
```python
@step
def fetch_weather(previous_output, start_date, end_date):
    # previous_output: result from previous step (e.g., tuple(lat, lon))
    # start_date, end_date: flow kwargs passed via .next()
    lat, lon = previous_output
    return fetch(lat, lon, start_date, end_date)

@flow
def weather_flow(location="New York", start_date="2024-01-01"):
    return (
        geocode_location(location)  # Returns (lat, lon)
        .next(fetch_weather, start_date=start_date, end_date="2024-01-31")
    )
```

**Key points:**
- The first parameter is **always** the previous step's output
- Flow-level kwargs are **always** keyword-only parameters
- This pattern eliminates the need to thread parameters through intermediate steps

### Flow-level parameters with `.map()` and `.agg()`

The `.map()` and `.agg()` methods also support flow-level parameters:

```python
@step
def get_items():
    return [1, 2, 3]

@step
def process_item(item, multiplier):
    return item * multiplier

@step
def aggregate_all(results, initial_value=0):
    return sum(results) + initial_value

@flow
def flow_with_map_params(multiplier=2, initial_value=10):
    return (
        get_items()
        .map(process_item, multiplier=multiplier)
        .agg(aggregate_all, initial_value=initial_value)
    )
```

**Behavior:**
- `.map(step, **flow_kwargs)` - Each mapped step receives flow kwargs in addition to the item
- `.agg(step, **flow_kwargs)` - The aggregation step receives flow kwargs in addition to the collected results

**Parameter resolution for `.map()`:**
```python
@step
def process_with_config(item, config_value):
    # item: each element from previous step's list
    # config_value: flow kwargs passed via .map()
    return item * config_value

@flow
def map_flow(config_value=5):
    return get_items().map(process_with_config, config_value=config_value)
```

**Parameter resolution for `.agg()`:**
```python
@step
def aggregate_with_seed(results, seed=0):
    # results: collected list from map block
    # seed: flow kwargs passed via .agg()
    return sum(results) + seed

@flow
def agg_flow(seed=100):
    return get_items().map(process_item).agg(aggregate_with_seed, seed=seed)
```

**Comparison:**

| Method | Input | Flow kwargs | Output | Use Case |
|--------|-------|-------------|--------|------------|
| `.map(step)` | list | no | list (per-item) | Parallel processing |
| `.map(step, kwarg=val)` | list + kwargs | yes | list (per-item) | Parallel with config |
| `.agg(step)` | list | no | single value | Aggregation |
| `.agg(step, kwarg=val)` | list + kwargs | yes | single value | Aggregation with config |
| `.next(step)` | previous output | no | any | Sequential chain |
| `.next(step, kwarg=val)` | prev output + kwargs | yes | any | Sequential with config |

**Error conditions:**
- Flow ending with an open Map block (without `.agg()`) must raise an exception
- Nested `.map()` calls are not supported and should raise an exception

---

## 4. Execution Graph

`FlowGraph._resolve()` performs a linear walk of the chain, collecting nodes into an ordered list of `GraphEntry` objects. Each entry is one of:

```python
@dataclass
class TaskEntry:
    node: StepNode

@dataclass
class MapOpenEntry:
    source: StepNode
    inner_steps: list[StepNode]

@dataclass
class MapCloseEntry:
    agg_step: StepNode
```

The resolved `entries: list[TaskEntry | MapOpenEntry | MapCloseEntry]` is the single representation consumed by both the local runner and all builders. This keeps the graph resolution logic in one place.

**Example — birds flow resolved entries:**

```
TaskEntry(get_birds)
MapOpenEntry(source=get_birds, inner_steps=[flap_bird])
MapCloseEntry(agg_step=join_birds)
```

---

## 5. CLI Entry Point

The CLI is implemented using Python's `argparse` module for consistent command-line parsing and help text. Each flow script uses the `main` function from lokki as the entry point:

```python
# flow_script.py
from lokki import flow, step, main

@step
def get_data(start_date: str, limit: int = 100):
    return [start_date] * limit

@flow
def my_flow(start_date: str, limit: int = 100):
    return get_data(start_date, limit)

if __name__ == "__main__":
    main(my_flow)
```

### Command Structure

| Command | Description |
|---------|-------------|
| `run` | Execute the pipeline locally |
| `build` | Package and generate deployment artifacts |
| `deploy` | Build and deploy to AWS |
| `show` | Show status of flow runs on AWS |
| `logs` | Fetch CloudWatch logs for a flow run |
| `destroy` | Destroy the AWS CloudFormation stack |

### Run Command

The `run` command supports passing input parameters to the flow function:

```bash
python flow_script.py run --start-date 2024-01-15 --limit 50
python flow_script.py run --start-date=2024-01-15 --limit=50
```

**Parameter handling:**
- Parameters are passed as `--param-name value` or `--param-name=value`
- Parameter names must match the flow function parameter names exactly
- Parameters without default values are **mandatory** - error if not provided
- Parameters with default values are **optional** - uses default if not provided
- Type validation is performed based on the flow function's type hints

### Parameter Validation

The CLI validates input parameters before execution:

1. **Existence check**: All mandatory parameters (those without defaults) must be provided
2. **Type validation**: Values are coerced to match the flow function's type hints
3. **Unknown parameters**: Extra parameters not in the flow function signature cause an error

**Supported type conversions:**
| Python Type | Example Input | Notes |
|-------------|---------------|-------|
| `str` | `--name john` | Default if no type hint |
| `int` | `--count 42` | Raises error on invalid int |
| `float` | `--rate 3.14` | Raises error on invalid float |
| `bool` | `--flag true` | Accepts true/false, 1/0 |
| `list[str]` | `--items a,b,c` | Comma-separated values |
| `list[int]` | `--ids 1,2,3` | Comma-separated integers |

**Validation errors:**
- Missing mandatory parameter: `Error: Missing required parameter: '--start-date'`
- Invalid type: `Error: Invalid value for '--count': 'abc' is not a valid integer`
- Unknown parameter: `Error: Unexpected parameter: '--unknown-param'`

### Argparse Integration

The `main` function in `lokki/__init__.py` uses `argparse` with subparsers for each command:

```python
def main(flow_fn: Callable[[], FlowGraph]) -> None:
    parser = argparse.ArgumentParser(prog="flow_script.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command with flow params
    run_parser = subparsers.add_parser("run", help="Run the flow locally")
    # Add flow function parameters as argparse arguments
    
    # build command
    subparsers.add_parser("build", help="Build deployment artifacts")
    
    # deploy command  
    subparsers.add_parser("deploy", help="Build and deploy to AWS")
    
    # show command
    show_parser = subparsers.add_parser("show", help="Show flow run status")
    show_parser.add_argument("--n", type=int, default=10, help="Number of runs to show")
    show_parser.add_argument("--run", type=str, help="Show specific run ID")
    
    # logs command
    logs_parser = subparsers.add_parser("logs", help="Fetch CloudWatch logs")
    logs_parser.add_argument("--start", type=str, help="Start datetime (ISO 8601)")
    logs_parser.add_argument("--end", type=str, help="End datetime (ISO 8601)")
    logs_parser.add_argument("--tail", action="store_true", help="Tail logs in real-time")
    logs_parser.add_argument("--run", type=str, help="Specific run ID")
    
    # destroy command
    destroy_parser = subparsers.add_parser("destroy", help="Destroy the CloudFormation stack")
    destroy_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
```

### Subcommand Dispatch

| Subcommand | Action |
|------------|--------|
| `run` | Parse flow params → Validate → Call `LocalRunner.run(graph, params)` |
| `build` | Call `Builder.build(graph, config)` |
| `deploy` | Build → Push images → Deploy CloudFormation stack |
| `show` | List or show status of flow executions from Step Functions |
| `logs` | Fetch CloudWatch logs for Lambda functions |
| `destroy` | Delete CloudFormation stack after confirmation |

---

## Show Command

The `show` command retrieves and displays the status of flow runs from AWS Step Functions.

```bash
# Show last 10 runs (default)
python flow_script.py show

# Show last N runs
python flow_script.py show --n 5

# Show specific run
python flow_script.py show --run abc123-def456
```

**Options:**
| Option | Description |
|--------|-------------|
| `--n COUNT` | Number of recent runs to display (default: 10) |
| `--run RUN_ID` | Show details for a specific run ID |

**Output format:**
```
Run ID                    Status      Start Time              Duration
abc123-def456            SUCCEEDED   2024-01-15T10:30:00Z   2m 34s
ghi789-jkl012            FAILED      2024-01-15T10:25:00Z   1m 12s
mno345-pqr678            RUNNING     2024-01-15T10:20:00Z   -
```

**Implementation:**
- Uses AWS SDK (boto3) to call `list_executions` on the Step Functions state machine
- Filters by status if needed (optional)
- Returns execution name, status, start time, and stop time (if completed)
- Supports LocalStack endpoint if configured

---

## Logs Command

The `logs` command fetches CloudWatch logs for the flow's Lambda functions.

```bash
# Fetch logs for last run (default)
python flow_script.py logs

# Fetch logs for specific run
python flow_script.py logs --run abc123-def456

# Fetch logs with time range
python flow_script.py logs --start 2024-01-15T10:00:00Z --end 2024-01-15T12:00:00Z

# Tail logs in real-time
python flow_script.py logs --tail

# Combine options
python flow_script.py logs --run abc123-def456 --tail
```

**Options:**
| Option | Description |
|--------|-------------|
| `--start DATETIME` | Start time in ISO 8601 format (default: 1 hour ago) |
| `--end DATETIME` | End time in ISO 8601 format (default: now) |
| `--run RUN_ID` | Fetch logs for a specific run ID |
| `--tail` | Continuously poll and display new log entries |

**Output:**
- Fetches logs from all Lambda functions in the flow
- Groups logs by function name
- Displays timestamp, function name, and log message
- For `--tail`, updates in real-time until interrupted

**Implementation:**
- Uses AWS SDK to call `filter_log_events` on CloudWatch Logs
- Queries log groups using pattern: `/aws/lambda/{flow-name}-{step-name}`
- Queries all step functions in the flow (fetches step names from flow graph)
- Supports LocalStack endpoint if configured
- For `--tail`, polls every 2 seconds

---

## Destroy Command

The `destroy` command deletes the CloudFormation stack and associated resources.

```bash
# Destroy with confirmation prompt
python flow_script.py destroy

# Destroy without confirmation (for CI/CD)
python flow_script.py destroy --confirm
```

**Options:**
| Option | Description |
|--------|-------------|
| `--confirm` | Skip confirmation prompt and destroy immediately |

**Behavior:**
1. Validates AWS credentials
2. Shows what will be deleted (stack name)
3. Prompts for confirmation (unless `--confirm` is passed)
4. Deletes the CloudFormation stack
5. Waits for stack deletion to complete
6. Reports success or failure

**Confirmation prompt:**
```
This will delete the CloudFormation stack 'my-flow-stack' and all associated resources.
Are you sure you want to continue? (y/N):
```

**Implementation:**
- Uses AWS SDK to call `delete_stack` on CloudFormation
- Uses `wait_until_stack_deleted` to wait for completion
- Handles stack not found errors gracefully
- Supports LocalStack endpoint if configured

### Subcommand Dispatch

| Subcommand | Action |
|------------|--------|
| `run` | Parse flow params → Validate → Call `LocalRunner.run(graph, params)` |
| `build` | Call `Builder.build(graph, config)` |
| `deploy` | Build → Push images → Deploy CloudFormation stack |
| `show` | List or show status of flow executions from Step Functions |
| `logs` | Fetch CloudWatch logs for Lambda functions |
| `destroy` | Delete CloudFormation stack after confirmation |

---

## 6. Local Runner

`lokki/runner.py` executes the pipeline in-process, using a temporary directory as the intermediate data store instead of S3.

```python
class LocalRunner:
    def run(self, graph: FlowGraph):
        store = LocalStore(base_dir=tempfile.mkdtemp())
        for entry in graph.entries:
            if isinstance(entry, TaskEntry):
                self._run_task(entry.node, store)
            elif isinstance(entry, MapOpenEntry):
                self._run_map(entry, store)
            elif isinstance(entry, MapCloseEntry):
                self._run_agg(entry.agg_step, store)
```

- `LocalStore` mirrors the `S3Store` interface (read/write gzip pickle) but operates on the local filesystem. This allows the runtime wrapper logic to be shared between local and Lambda execution.
- Map fan-out is executed using `concurrent.futures.ThreadPoolExecutor` (or `ProcessPoolExecutor` for CPU-bound steps — defaulting to threads for simplicity in v1).
- Intermediate outputs are stored as `<tmpdir>/<step_name>.pkl.gz`.

### Retry Handling

When a step has retry configuration, the local runner implements retry logic:

```python
def _run_task_with_retry(self, node: StepNode, input_data: Any, store: LocalStore) -> Any:
    """Execute a step with retry logic."""
    config = node.retry
    last_exception: Exception | None = None
    
    for attempt in range(config.retries + 1):
        try:
            result = self._execute_step(node.fn, input_data)
            return result
        except config.exceptions as e:
            last_exception = e
            if attempt < config.retries:
                delay = min(config.delay * (config.backoff ** attempt), config.max_delay)
                time.sleep(delay)
    
    raise last_exception
```

- The step function is executed once initially, plus `retries` additional attempts on failure
- Between retries, exponential backoff is applied: `delay × backoff^attempt`
- Delay is capped at `max_delay` seconds
- Only configured exception types trigger retries (default: all exceptions)
- If all retries fail, the last exception is raised

---

## 7. Build Pipeline

`lokki/builder/builder.py` orchestrates the full build. Output is written to a `./lokki-build/` directory by default (configurable).

```
lokki-build/
├── lambdas/
│   ├── get_birds/
│   │   ├── Dockerfile
│   │   └── handler.py          # thin entrypoint that imports runtime/handler.py
│   ├── flap_bird/
│   │   ├── Dockerfile
│   │   └── handler.py
│   └── join_birds/
│       ├── Dockerfile
│       └── handler.py
├── statemachine.json
├── template.yaml
└── sam.yaml                    # For LocalStack testing
```

> **Note**: For ZIP-based deployments (used for LocalStack testing), the structure differs. See [Section 17: Local Deployment with SAM/LocalStack](#17-local-deployment-with-samlocalstack).

Build steps in order:

1. Resolve the `FlowGraph` from the flow function.
2. For each `StepNode` in `graph.nodes`, generate a Lambda directory (`lambda_pkg.py`).
3. Generate `statemachine.json` (`state_machine.py`).
4. Generate `template.yaml` (`cloudformation.py`).

---

## 8. S3 & Serialisation Layer

`lokki/s3.py` provides a thin wrapper around `boto3` for reading and writing gzip-compressed pickle objects.

```python
import gzip, pickle, boto3

def write(bucket: str, key: str, obj: Any) -> str:
    """Serialise obj, upload to s3://bucket/key, return the S3 URL."""
    data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=data)
    return f"s3://{bucket}/{key}"

def read(url: str) -> Any:
    """Download from S3 URL and deserialise."""
    bucket, key = _parse_url(url)
    data = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    return pickle.loads(gzip.decompress(data))
```

**Key naming convention:**

```
lokki/<flow_name>/<run_id>/<step_name>/output.pkl.gz
```

`run_id` is the Step Functions execution name, passed to each Lambda via an environment variable injected by the state machine context (`$$.Execution.Name`).

For Map states, each parallel invocation writes to:
```
lokki/<flow_name>/<run_id>/<step_name>/<item_index>/output.pkl.gz
```

The aggregation step receives a list of these URLs, downloads each, and merges them into a single list before invoking the user's function.

---

## 9. State Machine Generation

`lokki/builder/state_machine.py` walks `graph.entries` and emits an AWS Step Functions state machine definition (Amazon States Language JSON).

### State types used

| Graph entry | ASL state type |
|---|---|
| `TaskEntry` | `Task` — invokes the Lambda ARN |
| `MapOpenEntry` | `Map` (Distributed Map mode) with `ItemReader` pointing to an S3 JSON manifest |
| `MapCloseEntry` | `Task` for the aggregation Lambda, preceded by a state that writes collected results to S3 |

### Distributed Map pattern

The `Map` state uses `"Mode": "DISTRIBUTED"` and reads items from S3:

```json
{
  "Type": "Map",
  "ItemReader": {
    "Resource": "arn:aws:states:::s3:getObject",
    "ReaderConfig": { "InputType": "JSON", "MaxItems": 100000 },
    "Parameters": {
      "Bucket": "<bucket>",
      "Key.$": "$.map_manifest_key"
    }
  },
  "ItemProcessor": {
    "ProcessorConfig": { "Mode": "DISTRIBUTED", "ExecutionType": "STANDARD" },
    "StartAt": "<inner_first_state>",
    "States": { ... }
  },
  "ResultWriter": {
    "Resource": "arn:aws:states:::s3:putObject",
    "Parameters": {
      "Bucket": "<bucket>",
      "Prefix.$": "States.Format('lokki/{}/{}/map_results/', <flow>, $.run_id)"
    }
  }
}
```

The preceding `Task` state (the `source` step) is responsible for writing its output list to S3 as the map manifest JSON, and placing the manifest key into the state output.

### Inter-state data passing

Each Task state's output is a small JSON object containing only the S3 URL of the result — never the payload itself. This keeps all Step Functions I/O well within the 256 KB state payload limit.

```json
{ "result_url": "s3://bucket/lokki/flow/run123/get_birds/output.pkl.gz" }
```

### State naming

States are named after the Python function: `GetBirds`, `FlapBird`, `JoinBirds` (PascalCase). The state machine is constructed directly as a Python dict in Amazon States Language format.

### Retry Configuration

When a step has retry configuration, the Task state includes a `Retry` field:

```json
{
  "Type": "Task",
  "Resource": "arn:aws:lambda:us-east-1:123456789:function:getBirds",
  "Retry": [
    {
      "ErrorEquals": ["Lambda.ServiceException", "Lambda.AWSException", "Lambda.SdkClientException"],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2.0
    }
  ],
  "Next": "FlapBird"
}
```

**Retry field generation rules:**

| Retry Config | Step Functions Field |
|--------------|---------------------|
| `retries` | `MaxAttempts` (retries + 1 for initial attempt) |
| `delay` | `IntervalSeconds` (rounded to integer) |
| `backoff` | `BackoffRate` |
| `exceptions` | `ErrorEquals` — maps Python exception to AWS error types |

**Exception mapping:**

| Python Exception | AWS ErrorEquals |
|-----------------|-----------------|
| `Exception` (default) | All standard Lambda errors |
| `ConnectionError` | `Lambda.SdkClientException` |
| `TimeoutError` | `Lambda.AWSException` |
| Custom | Custom error name |

> **Note**: AWS Step Functions retry behavior differs from local execution. The initial invocation counts as attempt 1, and `MaxAttempts` includes the initial attempt. For example, `retries: 3` means initial call + 3 retries = 4 total attempts, so `MaxAttempts` is set to 4.

---

## 10. CloudFormation Template Generation

`lokki/builder/cloudformation.py` produces a `template.yaml` with the following logical sections:

**Parameters**

```yaml
Parameters:
  FlowName: { Type: String }
  S3Bucket: { Type: String }
  ECRRepoPrefix: { Type: String }
  ImageTag: { Type: String, Default: latest }
  PackageType: { Type: String, Default: image }
```

**IAM**

- `LambdaExecutionRole`: allows `logs:*`, `s3:GetObject`, `s3:PutObject` on the lokki prefix.
- `StepFunctionsExecutionRole`: allows `lambda:InvokeFunction` on all step Lambdas, `s3:GetObject` / `s3:PutObject` for Distributed Map result writing, `states:StartExecution` for nested executions (if needed).

**Lambda Functions** (one per `@step`)

For container image deployments (`PackageType: Image`):

```yaml
GetBirdsFunction:
  Type: AWS::Lambda::Function
  Properties:
    FunctionName: !Sub "${FlowName}-get-birds"
    PackageType: Image
    Code:
      ImageUri: !Sub "${ECRRepoPrefix}/get_birds:${ImageTag}"
    Role: !GetAtt LambdaExecutionRole.Arn
    Timeout: 900
    MemorySize: 512
    Environment:
      Variables:
        LOKKI_S3_BUCKET: !Ref S3Bucket
        LOKKI_FLOW_NAME: !Ref FlowName
```

**CloudWatch Log Groups**

Each Lambda function automatically creates a CloudWatch log group at deployment time. The log group naming convention is:

```
/aws/lambda/{FlowName}-{step-name}
```

For example, for a flow named `birds-flow` with steps `get_birds`, `flap_bird`, and `join_birds`:

```
/aws/lambda/birds-flow-get-birds
/aws/lambda/birds-flow-flap-bird
/aws/lambda/birds-flow-join-birds
```

These log groups are created automatically by AWS Lambda when the function is first invoked. The `logs` CLI command queries these log groups to fetch execution logs.

The CloudFormation template includes an implicit log group resource (AWS Lambda creates it automatically), so no explicit `AWS::Logs::LogGroup` resource is required in the template.

For ZIP archive deployments (`PackageType: ZipFile`):

```yaml
GetBirdsFunction:
  Type: AWS::Lambda::Function
  Properties:
    FunctionName: !Sub "${FlowName}-get-birds"
    PackageType: ZipFile
    Code:
      ZipFile: |
        # Inlined handler code
    Role: !GetAtt LambdaExecutionRole.Arn
    Timeout: 900
    MemorySize: 512
    Environment:
      Variables:
        LOKKI_S3_BUCKET: !Ref S3Bucket
        LOKKI_FLOW_NAME: !Ref FlowName
```

**Step Functions State Machine**

```yaml
BirdsFlowStateMachine:
  Type: AWS::StepFunctions::StateMachine
  Properties:
    StateMachineName: !Sub "${FlowName}-state-machine"
    RoleArn: !GetAtt StepFunctionsExecutionRole.Arn
    DefinitionString: !Sub |
      <inlined statemachine.json with ${FlowName} substitutions>
```

The state machine JSON is inlined into the CloudFormation template using `!Sub` so Lambda ARNs resolve at deploy time via `!GetAtt <Function>.Arn`.

---

## 11. Lambda Packaging

`lokki/builder/lambda_pkg.py` generates one directory per step under `lokki-build/lambdas/<step_name>/`.

### Dockerfile

```dockerfile
FROM public.ecr.aws/lambda/python:latest AS builder

# Install uv
RUN pip install uv --no-cache-dir

WORKDIR /build

# Copy dependency manifest and lock file from build context
COPY pyproject.toml uv.lock ./

# Install all project dependencies into /build/deps
RUN uv pip install --system --no-cache -r pyproject.toml --target /build/deps

# ---- runtime image ----
FROM public.ecr.aws/lambda/python:latest

# Copy installed deps
COPY --from=builder /build/deps ${LAMBDA_TASK_ROOT}/

# Symlink the lokki library from the build context into the task root
# (avoids copying lokki source into every image separately)
COPY lokki/ ${LAMBDA_TASK_ROOT}/lokki/

# Copy the step-specific handler entrypoint
COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
```

> **Symlink note**: Docker `COPY` does not support host symlinks into the image in a way that persists as symlinks inside the container. Instead, the `lokki/` source tree is `COPY`-ed once per image from the build context. To minimise duplication, Docker layer caching means this layer is shared across all step images when built from the same context — effectively the same benefit as symlinking. If the project uses a monorepo and lokki is an editable install, the wheel can be built once and `COPY`-ed into each image.

### ZIP Archive Packaging

When `package_type = "zip"` is configured in `lokki.toml`, the build process generates ZIP archives instead of Docker images. This is useful for LocalStack testing or simpler deployment setups.

**Directory structure** (`lokki-build/lambdas/<step_name>/`):

```
get_birds/
├── requirements.txt    # Step-specific dependencies
├── handler.py          # Step entrypoint
└── function.zip       # ZIP archive for Lambda
```

**requirements.txt generation** — The build process:
1. Extracts the step's direct imports from the flow script
2. Generates a `requirements.txt` with only those dependencies
3. Downloads and includes the resolved packages in the ZIP

**handler.py** (per-step entrypoint):

```python
# lokki-build/lambdas/get_birds/handler.py (auto-generated)
from birds_flow_example import get_birds
from lokki.runtime.handler import make_handler

lambda_handler = make_handler(get_birds.fn)
```

**CloudFormation template** — Lambda functions use `PackageType: ZipFile`:

```yaml
GetBirdsFunction:
  Type: AWS::Lambda::Function
  Properties:
    FunctionName: !Sub "${FlowName}-get-birds"
    PackageType: ZipFile
    Code:
      ZipFile: |
        # Inline the handler.py content
    Role: !GetAtt LambdaExecutionRole.Arn
    Timeout: 900
    MemorySize: 512
```

> **Note**: For ZIP deployments, the CloudFormation template inlines the handler code directly rather than referencing an S3 object. This simplifies deployment but means the handler source is stored in the template itself.

### handler.py (per-step entrypoint)

A thin, auto-generated file that binds the specific step function to the generic runtime handler:

```python
# lokki-build/lambdas/get_birds/handler.py  (auto-generated)
from birds_flow_example import get_birds          # imports user's function
from lokki.runtime.handler import make_handler

lambda_handler = make_handler(get_birds.fn)
```

The build process writes one of these per step, importing the correct function from the user's flow script.

---

## 12. Runtime Wrapper (Lambda Handler)

`lokki/runtime/handler.py` contains `make_handler`, which wraps any user step function so it can run inside Lambda. This is the only lokki code that executes in production.

```python
def make_handler(fn: Callable, retry_config: RetryConfig | None = None) -> Callable:
    def lambda_handler(event: dict, context) -> dict:
        import inspect
        from lokki.s3 import read, write
        from lokki.config import get_config

        cfg = get_config()  # reads env vars: LOKKI_S3_BUCKET, LOKKI_FLOW_NAME
        run_id = event["run_id"]          # injected by Step Functions context
        step_name = fn.__name__

        # Resolve inputs: event may contain result_url (single) or result_urls (list for agg)
        if "result_url" in event:
            arg = read(event["result_url"])
            result = fn(arg)
        elif "result_urls" in event:
            args = [read(url) for url in event["result_urls"]]
            result = fn(args)
        else:
            # First step — no upstream input; use defaults or event overrides
            sig = inspect.signature(fn)
            kwargs = {k: event[k] for k in event if k in sig.parameters}
            result = fn(**kwargs)

        # Write output to S3
        key = f"lokki/{cfg.flow_name}/{run_id}/{step_name}/output.pkl.gz"
        url = write(cfg.bucket, key, result)

        return {"result_url": url, "run_id": run_id}

    return lambda_handler
```

For Map steps, the `source` step's handler additionally writes a manifest:

```python
# After writing output.pkl.gz, if result is a list:
manifest = [{"item": item_url, "index": i} for i, item_url in enumerate(item_urls)]
manifest_key = f"lokki/{flow_name}/{run_id}/{step_name}/map_manifest.json"
s3.put_object(Body=json.dumps(manifest), ...)
return {"map_manifest_key": manifest_key, "run_id": run_id}
```

> **Note**: For deployed flows, retry logic is handled by AWS Step Functions using the `Retry` field in the state machine definition. The Lambda handler doesn't implement retry logic — it just executes the step function once. The retry configuration is used during build time to generate the appropriate Step Functions retry policy.

---

## 13. Configuration

`lokki/config.py` is responsible for loading, merging, and exposing configuration to the rest of the library. Configuration is sourced from two `lokki.toml` files and environment variables, resolved in this order (highest precedence first):

```
environment variables → local lokki.toml → global ~/.lokki/lokki.toml → built-in defaults
```

### Loading & merging

```python
# lokki/config.py (simplified)
import os
import tomllib
from pathlib import Path
from dataclasses import dataclass, field

GLOBAL_CONFIG_PATH = Path.home() / ".lokki" / "lokki.toml"
LOCAL_CONFIG_PATH = Path.cwd() / "lokki.toml"

def _load_toml(path: Path) -> dict:
    if path.exists():
        with path.open("rb") as f:
            return tomllib.load(f)
    return {}

def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base. Scalars and lists are replaced; dicts are merged recursively."""
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value   # lists replaced entirely, not concatenated
    return result

def load_config() -> "LokkiConfig":
    global_cfg = _load_toml(GLOBAL_CONFIG_PATH)
    local_cfg = _load_toml(LOCAL_CONFIG_PATH)
    merged = _deep_merge(global_cfg, local_cfg)
    return LokkiConfig.from_dict(merged)


@dataclass
class LambdaConfig:
    package_type: str = "image"  # "image" or "zip"
    timeout: int = 900
    memory: int = 512
    image_tag: str = "latest"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class LokkiConfig:
    # Top-level fields
    build_dir: str = "lokki-build"

    # AWS configuration (from [aws] table)
    artifact_bucket: str = ""
    image_repository: str = ""  # "local", "docker.io", or ECR prefix
    aws_endpoint: str = ""
    stepfunctions_role: str = ""
    lambda_execution_role: str = ""

    # Nested config
    lambda_cfg: LambdaConfig = field(default_factory=LambdaConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_dict(cls, d: dict) -> "LokkiConfig":
        """Create a LokkiConfig from a dictionary."""
        aws_config = d.get("aws", {})
        lambda_config = d.get("lambda", {})
        logging_config = d.get("logging", {})

        lambda_cfg = LambdaConfig(
            package_type=lambda_config.get("package_type", "image"),
            timeout=lambda_config.get("timeout", 900),
            memory=lambda_config.get("memory", 512),
            image_tag=lambda_config.get("image_tag", "latest"),
            env=lambda_config.get("env", {}),
        )
        return cls(
            build_dir=d.get("build_dir", "lokki-build"),
            artifact_bucket=aws_config.get("artifact_bucket", ""),
            image_repository=aws_config.get("image_repository", ""),
            aws_endpoint=aws_config.get("endpoint", ""),
            stepfunctions_role=aws_config.get("stepfunctions_role", ""),
            lambda_execution_role=aws_config.get("lambda_execution_role", ""),
            lambda_cfg=lambda_cfg,
            logging=LoggingConfig(
                level=logging_config.get("level", "INFO"),
                format=logging_config.get("format", "human"),
                progress_interval=logging_config.get("progress_interval", 10),
                show_timestamps=logging_config.get("show_timestamps", True),
            ),
        )
```

### Example lokki.toml

```toml
# lokki.toml

# Output directory for build artifacts (default: lokki-build)
build_dir = "lokki-build"

[aws]

# S3 bucket for intermediate pipeline data and build artifacts
artifact_bucket = "my-lokki-artifacts"

# Docker repository: "local", "docker.io", or ECR prefix
image_repository = "123456789.dkr.ecr.us-east-1.amazonaws.com/myproject"

# AWS endpoint for local development (e.g., LocalStack)
endpoint = "http://localhost:4566"

# IAM role ARNs
stepfunctions_role = "arn:aws:iam::123456789::role/lokki-stepfunctions-role"
lambda_execution_role = "arn:aws:iam::123456789::role/lokki-lambda-execution-role"

[lambda]
package_type = "image"
timeout = 900
memory = 512
image_tag = "latest"

[lambda.env]
LOG_LEVEL = "INFO"

[logging]
level = "INFO"
format = "human"
```

[logging]
level = "INFO"
format = "human"
```

### Environment variable overrides

After loading and merging the TOML files, specific fields can be overridden by environment variables. This is primarily useful inside Lambda functions at runtime, where the full `lokki.toml` is not available.

| Environment variable | Overrides field |
|---|---|
| `LOKKI_ARTIFACT_BUCKET` | `artifact_bucket` |
| `LOKKI_IMAGE_REPOSITORY` | `image_repository` |
| `LOKKI_AWS_ENDPOINT` | `aws_endpoint` |
| `LOKKI_BUILD_DIR` | `build_dir` |
| `LOKKI_LOG_LEVEL` | `logging.level` |

### Usage at build time vs runtime

At **build time** (`python flow_script.py build`), `load_config()` reads both TOML files from the filesystem and uses the merged result to populate the CloudFormation template and Dockerfiles (e.g. IAM role ARNs, image repository, artifact bucket name). The flow name is derived directly from the `@flow`-decorated function name (e.g. `birds_flow` → `"birds-flow"`, lowercased and underscores replaced with hyphens) and is not configurable — it is baked into the CloudFormation resource names and S3 key prefixes at build time.

At **Lambda runtime**, the TOML files are not present. The Lambda functions receive their configuration entirely through environment variables injected by CloudFormation at deploy time — `LOKKI_ARTIFACT_BUCKET`, `LOKKI_FLOW_NAME` (set to the derived flow name), and any entries from `lambda.env` in the config.

---

## 14. Data Flow Walkthrough

End-to-end flow for `birds_flow` deployed on AWS:

```
StepFunctions execution starts
│
│  Input JSON (optional overrides): {}
│
├─► GetBirds Lambda
│     handler reads: no upstream input (first step)
│     fn returns: ["goose", "duck", "seagul"]
│     writes: s3://bucket/lokki/birds_flow/<run_id>/get_birds/output.pkl.gz
│     also writes map manifest JSON (list of per-item S3 write targets)
│     returns: { "map_manifest_key": "lokki/.../map_manifest.json", "run_id": "..." }
│
├─► Distributed Map state (reads manifest from S3)
│   │
│   ├─► FlapBird Lambda [item=0: "goose"]
│   │     reads: item from manifest → "goose" (the item itself is small, passed inline)
│   │     fn returns: "flappy goose"
│   │     writes: s3://.../flap_bird/0/output.pkl.gz
│   │     returns: { "result_url": "s3://.../flap_bird/0/output.pkl.gz" }
│   │
│   ├─► FlapBird Lambda [item=1: "duck"]  (parallel)
│   │     writes: s3://.../flap_bird/1/output.pkl.gz
│   │
│   └─► FlapBird Lambda [item=2: "seagul"]  (parallel)
│         writes: s3://.../flap_bird/2/output.pkl.gz
│
│   Map ResultWriter collects all result URLs → writes results index to S3
│
├─► JoinBirds Lambda
│     handler reads: result_urls list → downloads all FlapBird outputs
│     assembles: ["flappy goose", "flappy duck", "flappy seagul"]
│     fn returns: "flappy goose, flappy duck, flappy seagul"
│     writes: s3://.../join_birds/output.pkl.gz
│     returns: { "result_url": "s3://.../join_birds/output.pkl.gz" }
│
StepFunctions execution completes
Final output: { "result_url": "s3://bucket/lokki/birds_flow/<run_id>/join_birds/output.pkl.gz" }
```

---

## 15. Logging & Observability

### Design Goals

- **Human-readable by default** — useful for local development and CLI
- **Optional structured JSON** — for production log aggregation
- **Minimal overhead** — logging should not significantly impact execution time
- **Consistent format** — predictable log structure across all components

### Logger Module

`lokki/logging.py` provides the logging infrastructure:

```python
# lokki/logging.py (simplified)

import logging
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any

class LogFormat(Enum):
    HUMAN = "human"
    JSON = "json"

@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: LogFormat = LogFormat.HUMAN
    progress_interval: int = 10
    show_timestamps: bool = True

def get_logger(name: str, config: LoggingConfig) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.level))
    
    handler = logging.StreamHandler(sys.stdout)
    if config.format == LogFormat.JSON:
        handler.setFormatter(JsonFormatter(config))
    else:
        handler.setFormatter(HumanFormatter(config))
    
    logger.addHandler(handler)
    return logger
```

### Step Lifecycle Events

The local runner logs step execution events:

```
[INFO] Step 'get_birds' started at 2024-01-15T10:30:00
[INFO] Step 'get_birds' completed in 0.123s (status=success)
[ERROR] Step 'process_data' failed after 2.456s: ValueError: invalid input
```

### Map Progress Tracking

For `.map()` blocks, progress is tracked per item:

```python
class MapProgressLogger:
    def __init__(self, step_name: str, total_items: int, config: LoggingConfig):
        self.step_name = step_name
        self.total_items = total_items
        self.completed = 0
        self.failed = 0
        self._last_pct = -1
    
    def update(self, status: str):
        """Call when an item completes: status = 'completed' or 'failed'"""
        if status == "completed":
            self.completed += 1
        elif status == "failed":
            self.failed += 1
        
        pct = int(100 * self.completed / self.total_items)
        if pct >= self._last_pct + 10:
            self._last_pct = pct
            self._log_progress()
    
    def _log_progress(self):
        bar_len = 20
        filled = int(bar_len * self.completed / self.total_items)
        bar = "=" * filled + ">" + " " * (bar_len - filled)
        logger.info(f"  [{bar}] {self.completed}/{self.total_items} ({pct}%)")
```

Output:
```
[INFO] Map 'process_items' started (100 items)
[INFO]   [=====>                    ] 30/100 (30%)
[INFO]   [=============>             ] 60/100 (60%)
[INFO]   [=========================>] 100/100 (100%)
[INFO] Map 'process_items' completed in 4.567s
```

### JSON Structured Logging

When `format: json` is configured, each log line is a JSON object:

```python
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json
        return json.dumps({
            "level": record.levelname,
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": getattr(record, "event", "log"),
            "step": getattr(record, "step", ""),
            "duration": getattr(record, "duration", None),
            "status": getattr(record, "status", ""),
            "message": record.getMessage(),
        })
```

Example output:
```json
{"level": "INFO", "ts": "2024-01-15T10:30:00.123Z", "event": "step_start", "step": "get_data", "run_id": "abc123"}
{"level": "INFO", "ts": "2024-01-15T10:30:02.456Z", "event": "step_complete", "step": "get_data", "duration": 2.333, "status": "success"}
{"level": "INFO", "ts": "2024-01-15T10:30:02.789Z", "event": "map_progress", "step": "process", "total": 100, "completed": 50, "failed": 0}
```

### Configuration Integration

Logging configuration is added to the existing config system:

```python
@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "human"  # "human" or "json"
    progress_interval: int = 10
    show_timestamps: bool = True

@dataclass
class LokkiConfig:
    # ... existing fields ...
    logging: LoggingConfig = field(default_factory=LoggingConfig)
```

Environment variable override: `LOKKI_LOG_LEVEL`

### Integration Points

1. **LocalRunner** — wraps `_run_task()`, `_run_map()`, `_run_agg()` with logging
2. **Runtime Handler** — logs Lambda invocation, input processing, duration, errors
3. **Builder** — optional build progress logging (less critical)

### Thread Safety

The `MapProgressLogger` uses simple counters which are thread-safe in Python due to the GIL. For more complex scenarios, a `threading.Lock` can be used.

### CloudWatch Integration

In Lambda, logs automatically go to CloudWatch. The JSON format is particularly useful for CloudWatch Logs Insights queries:

```sql
fields @timestamp, event, step, duration
| filter level = 'ERROR'
| sort @timestamp desc
```

---

## 16. Deploy Command

The `deploy` command builds the flow and deploys it to AWS. It combines the build step with AWS deployment operations.

### Architecture

```
python flow_script.py deploy
         │
         ▼
┌─────────────────────────────────────┐
│          deploy.py                   │
│  1. Validate AWS credentials       │
│  2. Build (reuse Builder.build)    │
│  3. Push Lambda images to ECR      │
│  4. Deploy CloudFormation stack    │
└─────────────────────────────────────┘
```

### Implementation

`lokki/deploy.py` contains the deployment logic:

```python
# lokki/deploy.py (simplified)

import boto3
import subprocess
from pathlib import Path

from lokki.builder.builder import Builder
from lokki.config import load_config


class Deployer:
    def __init__(self, stack_name: str, region: str, image_tag: str):
        self.stack_name = stack_name
        self.region = region
        self.image_tag = image_tag
        self.cf_client = boto3.client("cloudformation", region_name=region)
        self.ecr_client = boto3.client("ecr")
        self.sts_client = boto3.client("sts")

    def deploy(self, graph: FlowGraph, config: LokkiConfig) -> None:
        # 1. Validate credentials
        self._validate_credentials()

        # 2. Build (reuse Builder)
        print("Building...")
        Builder.build(graph, config)

        # 3. Push Lambda images
        self._push_images(config.image_repository)

        # 4. Deploy CloudFormation
        self._deploy_stack(config)

    def _push_images(self, ecr_prefix: str) -> None:
        build_dir = Path(config.build_dir)
        for step_dir in (build_dir / "lambdas").iterdir():
            step_name = step_dir.name
            image_uri = f"{ecr_prefix}/{step_name}:{self.image_tag}"

            # Build and push
            subprocess.run(
                ["docker", "build", "-t", image_uri, "."],
                cwd=step_dir,
                check=True,
            )
            subprocess.run(
                ["docker", "push", image_uri],
                check=True,
            )

    def _deploy_stack(self, config: LokkiConfig) -> None:
        template_path = Path(config.build_dir) / "template.yaml"
        response = self.cf_client.create_or_update_stack(
            StackName=self.stack_name,
            TemplateBody=template_path.read_text(),
            Capabilities=["CAPABILITY_IAM"],
            Parameters=[
                {"ParameterKey": "FlowName", "ParameterValue": config.flow_name},
                {"ParameterKey": "S3Bucket", "ParameterValue": config.artifact_bucket},
                {"ParameterKey": "ImageRepository", "ParameterValue": config.image_repository},
                {"ParameterKey": "ImageTag", "ParameterValue": self.image_tag},
            ],
        )
        print(f"Deployed stack: {self.stack_name}")
```

### CLI Integration

The @flow function in `__init__.py` is extended to handle the `deploy` command:

```python
elif command == "deploy":
    from lokki.deploy import Deployer
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--stack-name")
    parser.add_argument("--region")
    parser.add_argument("--image-tag", default="latest")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(sys.argv[2:])

    graph = flow_fn()
    config = load_config()

    deployer = Deployer(
        stack_name=args.stack_name or f"{graph.name}-stack",
        region=args.region or "us-east-1",
        image_tag=args.image_tag,
    )
    deployer.deploy(graph, config)
```

### Image Build Strategy

For Lambda container images, all steps share a single Docker image. The deploy command:

1. Builds a single Docker image from `lokki-build/lambdas/Dockerfile`
2. Tags with `<image_repository>/lokki:<image_tag>`
3. Pushes to registry using `docker push`
4. Each Lambda function in CloudFormation references the same image URI

**Handler Dispatch:**
The shared Docker image contains a single handler that dispatches to the correct step function based on environment variables:
- `LOKKI_STEP_NAME`: Name of the step function to invoke
- `LOKKI_MODULE_NAME`: Python module name containing the flow (e.g., `birds_flow`)

The handler imports the module dynamically and calls the appropriate step function. This allows a single image to serve all steps in a flow.

**Dependencies:**
The user's flow project must include `lokki` in its `pyproject.toml` dependencies. The Lambda image installs all dependencies from the user's `pyproject.toml` using `uv pip install`.

This requires Docker to be installed and running on the developer's machine.

### Error Handling

- **No Docker**: Raises error if Docker is not available
- **ECR auth failure**: Prompts to run `aws ecr get-login-password`
- **CloudFormation failure**: Displays error message and stack events
- **Partial failure**: Images already pushed remain in ECR; re-running deploy will continue from where it failed

### Idempotency

The deploy command is idempotent - running it multiple times with the same parameters will update the CloudFormation stack. Images are re-tagged and pushed on each run.

---

## 17. Local Deployment with SAM/LocalStack

For local development and testing, lokki supports ZIP-based deployment with SAM CLI and LocalStack. This allows testing the full pipeline locally without deploying to real AWS.

### Configuration

In `lokki.toml`, set `package_type = "zip"`:

```toml
[lambda]
package_type = "zip"  # Use "zip" for LocalStack testing; "image" for production
timeout = 900
memory = 512
```

For LocalStack, configure the endpoint:

```yaml
aws:
  profile: local
  artifact_bucket: lokki
  endpoint: http://localhost:4566
```

### Build Output

When `package_type: zip` is set, the build generates:

```
lokki-build/
├── lambdas/
│   ├── function.zip      # Single ZIP with all dependencies
│   ├── handler.py       # Dispatcher handler
│   ├── lokki/          # lokki runtime code
│   └── birds_flow_example.py  # User's flow module
├── statemachine.json
├── template.yaml        # CloudFormation (for real AWS)
└── sam.yaml            # SAM template (for LocalStack)
```

### Single ZIP Package

Instead of per-step Docker images, a single `function.zip` is created containing:
- All dependencies (boto3, etc.)
- lokki runtime code
- User's flow module (e.g., `birds_flow_example.py`)

### Dispatcher Handler

A single `handler.py` dispatches to the correct step function based on the `LOKKI_STEP_NAME` environment variable:

```python
# handler.py (auto-generated)
import os
import importlib

step_name = os.environ.get("LOKKI_STEP_NAME", "")
module_name = os.environ.get("LOKKI_MODULE_NAME", "")

mod = importlib.import_module(module_name)
step_node = getattr(mod, step_name)
step_func = step_node.fn if hasattr(step_node, 'fn') else step_node

from lokki.runtime.handler import make_handler
lambda_handler = make_handler(step_func)
```

### SAM Template

The `sam.yaml` template defines Lambda functions using the ZIP package:

```yaml
GetBirdsFunction:
  Type: AWS::Serverless::Function
  Properties:
    FunctionName: birds-flow-get_birds
    Runtime: python3.13
    Handler: handler.lambda_handler
    CodeUri: lambdas/function.zip
    Environment:
      Variables:
        LOKKI_S3_BUCKET: lokki
        LOKKI_FLOW_NAME: birds-flow
        LOKKI_AWS_ENDPOINT: http://host.docker.internal:4566
        LOKKI_STEP_NAME: get_birds
        LOKKI_MODULE_NAME: birds_flow_example
```

**Key environment variables:**
- `LOKKI_S3_BUCKET`: S3 bucket for pipeline data
- `LOKKI_FLOW_NAME`: Name of the flow
- `LOKKI_AWS_ENDPOINT`: Endpoint for SAM local invoke (LocalStack)
- `LOKKI_STEP_NAME`: Name of the step to invoke
- `LOKKI_MODULE_NAME`: Python module containing the flow

### S3 Endpoint Configuration

The lokki S3 module supports endpoint configuration for LocalStack:

```python
# lokki/s3.py
_endpoint: str = ""

def set_endpoint(endpoint: str) -> None:
    global _endpoint
    _endpoint = endpoint

def _get_s3_client():
    kwargs = {}
    if _endpoint:
        kwargs["endpoint_url"] = _endpoint
    return boto3.client("s3", **kwargs)
```

The runtime handler reads `LOKKI_AWS_ENDPOINT` and configures the S3 client:

```python
# lokki/runtime/handler.py
endpoint = os.environ.get("LOKKI_AWS_ENDPOINT", "")
if endpoint:
    s3.set_endpoint(endpoint)
```

### Deploy to LocalStack

The deploy command detects LocalStack (when `aws.endpoint` is configured) and uses AWS CLI with `--endpoint-url`:

```bash
python flow_script.py deploy --stack-name lokki-test --region us-east-1
```

Output:
```
Skipping Docker image push for ZIP deployment
Using SAM template for LocalStack deployment...
✓ Deployed stack 'lokki-test'
```

### Test Locally with SAM CLI

After deployment, test individual Lambda functions:

```bash
cd lokki-build

# Invoke a specific function
sam local invoke GetBirdsFunction --template sam.yaml --region us-east-1

# Or start a local Lambda endpoint
sam local start-lambda --template sam.yaml --port 3001
```

The Lambda container will write to LocalStack S3, which can be verified:

```bash
aws --endpoint-url=http://localhost:4566 s3 ls lokki/
```

### Workflow Summary

| Step | Command |
|------|---------|
| Build | `python flow_script.py build` |
| Deploy to LocalStack | `python flow_script.py deploy` |
| Test function | `sam local invoke GetBirdsFunction` |
| List S3 contents | `aws --endpoint-url=http://localhost:4566 s3 ls lokki/` |

---

## 17. AWS Batch Support

### Overview

AWS Batch support allows running compute-intensive steps as Batch jobs instead of Lambda functions. This is useful for:
- Workloads that exceed Lambda's 15-minute timeout
- Tasks requiring more than 10GB of storage
- Jobs needing more than 10GB memory
- GPU-enabled processing

### Architecture

```
┌─────────────────────────────────────────────┐
│              Step Functions                   │
│   (orchestrates Lambda and Batch jobs)       │
└───────────────┬─────────────────────────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
┌───────────────┐ ┌───────────────┐
│  Lambda       │ │  AWS Batch    │
│  Invoke       │ │  SubmitJob    │
│  (lightweight │ │  (heavy      │
│   tasks)      │ │   compute)   │
└───────────────┘ └───────────────┘
```

### Configuration

#### Global Batch Configuration

Batch settings are configured in `lokki.toml`:

```toml
[batch]
job_queue = "my-job-queue"
job_definition_name = "my-job-def"
timeout = 3600        # Default job timeout (seconds)
vcpu = 2              # Default vCPUs
memory_mb = 4096      # Default memory (MB)
image = ""            # Docker image (defaults to Lambda image if empty)
```

#### Step-Level Overrides

Each `@step` can override Batch configuration:

```python
@step(job_type="batch", vcpu=8, memory_mb=16384, timeout_seconds=7200)
def heavy_processing(data):
    return expensive_computation(data)
```

### Decorator Design

#### JobTypeConfig

```python
@dataclass
class JobTypeConfig:
    job_type: str = "lambda"  # "lambda" or "batch"
    vcpu: int | None = None   # None = use global config
    memory_mb: int | None = None
    timeout_seconds: int | None = None
```

#### StepNode Updates

The `StepNode` class is extended to store job type information:

```python
class StepNode:
    def __init__(
        self,
        fn: Callable[..., Any],
        retry: RetryConfig | None = None,
        job_type: str = "lambda",
        vcpu: int | None = None,
        memory_mb: int | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.fn = fn
        self.name = fn.__name__
        self.retry = retry or RetryConfig()
        self.job_type = job_type  # "lambda" or "batch"
        self.vcpu = vcpu
        self.memory_mb = memory_mb
        self.timeout_seconds = timeout_seconds
        # ... existing fields
```

#### @step Decorator

The decorator accepts job type parameters:

```python
def step(
    fn: Callable[..., Any] | None = None,
    *,
    retry: RetryConfig | dict[str, Any] | None = None,
    job_type: str = "lambda",
    vcpu: int | None = None,
    memory_mb: int | None = None,
    timeout_seconds: int | None = None,
) -> StepNode | Callable[[Callable[..., Any]], StepNode]:
    # ... implementation
```

### Execution Graph

The `FlowGraph` resolves job type information into the execution graph:

```python
@dataclass
class TaskEntry:
    node: StepNode
    job_type: str = "lambda"
    vcpu: int | None = None
    memory_mb: int | None = None
    timeout_seconds: int | None = None
```

During resolution, step-level values override global values:
- If `step.vcpu` is set, use it
- Else use `config.batch.vcpu`

### Runtime Handler

#### Lambda Handler (existing)

The Lambda handler (`lokki/runtime/handler.py`) remains unchanged for Lambda steps.

#### Batch Handler (new)

A new Batch handler (`lokki/runtime/batch.py`) handles Batch job execution:

```python
def make_batch_handler(
    fn: Callable[..., Any],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Create a handler for AWS Batch jobs."""
    
    def batch_handler(event: dict[str, Any]) -> dict[str, Any]:
        from lokki import s3
        from lokki._aws import get_batch_client
        
        cfg = load_config()
        batch_client = get_batch_client(cfg.aws_endpoint)
        
        # Read input from S3
        input_url = event.get("input_url")
        if input_url:
            input_data = s3.read(input_url)
        else:
            input_data = None
        
        # Execute the step function
        if input_data is not None:
            result = fn(input_data)
        else:
            result = fn()
        
        # Write output to S3
        output_url = s3.write(cfg.artifact_bucket, output_key, result)
        
        return {
            "result_url": output_url,
            "run_id": event.get("run_id", "unknown"),
        }
    
    return batch_handler
```

### State Machine Generation

The state machine generation is updated to support mixed Lambda/Batch steps:

#### Task State for Lambda (existing)

```json
{
  "Type": "Task",
  "Resource": "arn:aws:lambda:us-east-1:123456789:function:myflow-my_step",
  "Resource": "arn:aws:states:::lambda:invoke",
  "Parameters": {
    "FunctionName": "myflow-my_step",
    "Payload": {
      "input_url.$": "$.result.result_url",
      "run_id.$": "$$.Execution.Name"
    }
  },
  "ResultPath": "$.result"
}
```

#### Task State for Batch (new)

```json
{
  "Type": "Task",
  "Resource": "arn:aws:states:::batch:submitJob.sync",
  "Parameters": {
    "JobDefinition": {"Ref": "BatchJobDefinition"},
    "JobName.$": "States.Format('{}-{}', $.flow_name, $.step_name)",
    "JobQueue": {"Ref": "BatchJobQueue"},
    "ContainerOverrides": {
      "Vcpus.$": "$.vcpu",
      "Memory.$": "$.memory",
      "Command": ["python", "-m", "lokki.runtime.batch_main"]
    },
    "Environment": [
      {"Name": "LOKKI_S3_BUCKET", "Value.$": "$.s3_bucket"},
      {"Name": "LOKKI_FLOW_NAME", "Value.$": "$.flow_name"},
      {"Name": "LOKKI_STEP_NAME", "Value.$": "$.step_name"},
      {"Name": "LOKKI_RUN_ID", "Value.$": "$.run_id"},
      {"Name": "LOKKI_INPUT_URL", "Value.$": "$.result.result_url"}
    ]
  },
  "ResultPath": "$.result"
}
```

### CloudFormation Template

#### Parameters

```yaml
Parameters:
  BatchJobQueue:
    Type: String
    Default: ""
  BatchJobDefinitionName:
    Type: String
    Default: ""
```

#### Batch Job Definition

```yaml
BatchJobDefinition:
  Type: AWS::Batch::JobDefinition
  Properties:
    JobDefinitionName: !Sub "${FlowName}-job"
    Type: container
    ContainerProperties:
      Image: !Sub "${ECRRepoPrefix}/lokki:${ImageTag}"
      Vcpus: 2
      Memory: 4096
      JobRoleArn: !GetAtt BatchExecutionRole.Arn
      LogConfiguration:
        LogDriver: awslogs
        Options:
          "awslogs-group": !Ref AWS::NoValue
          "awslogs-region": !Ref AWS::Region
    RetryStrategy:
      Attempts: 1
```

#### Batch Execution Role

```yaml
BatchExecutionRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal: { Service: "ecs-tasks.amazonaws.com" }
          Action: "sts:AssumeRole"
    Policies:
      - PolicyName: S3Access
        PolicyDocument:
          Version: "2012-10-17"
          Statement:
            - Effect: Allow
              Action:
                - s3:GetObject
                - s3:PutObject
              Resource:
                - !Sub "arn:aws:s3:::${S3Bucket}/lokki/*"
      - PolicyName: LogsAccess
        PolicyDocument:
          Version: "2012-10-17"
          Statement:
            - Effect: Allow
              Action:
                - logs:CreateLogGroup
                - logs:CreateLogStream
                - logs:PutLogEvents
              Resource: "*"
```

#### Step Functions Role Updates

```yaml
- PolicyName: BatchAccess
  PolicyDocument:
    Version: "2012-10-17"
    Statement:
      - Effect: Allow
        Action:
          - batch:SubmitJob
          - batch:DescribeJobs
          - batch:TerminateJob
        Resource: "*"
```

### Local Runner

For local testing, Batch steps execute inline using moto for realistic mocking:

```python
class LocalRunner:
    def _run_task(self, entry: TaskEntry, store: LocalStore) -> Any:
        job_type = entry.job_type
        
        if job_type == "batch":
            return self._run_batch_task_inline(entry, store)
        else:
            return self._run_lambda_task(entry, store)
    
    def _run_batch_task_inline(self, entry: TaskEntry, store: LocalStore) -> Any:
        """Run Batch step inline with mocked Batch submission."""
        # Use moto to mock Batch API
        # Submit job (mocked), wait for completion, get result
        # For simplicity, execute function directly in tests
        pass
```

### Data Flow Walkthrough (Batch)

```
StepFunctions execution starts
│
├─► GetBirds Lambda (job_type=lambda)
│     handler reads: no upstream input
│     writes: s3://bucket/lokki/flow/run_id/get_birds/output.pkl.gz
│     returns: { "result_url": "s3://...", "run_id": "..." }
│
├─► Distributed Map (reads from S3)
│   │
│   ├─► ProcessItem Batch Job (job_type=batch)
│   │     batch_handler reads: s3://bucket/lokki/flow/run_id/.../0/input.pkl.gz
│   │     executes: fn(item)
│   │     writes: s3://bucket/lokki/flow/run_id/process_item/0/output.pkl.gz
│   │     returns: { "result_url": "s3://..." }
│   │
│   └─► ResultWriter writes all results to S3
│
├─► SaveResults Lambda (job_type=lambda)
│     reads: list of result URLs
│     writes: final output to S3
│
StepFunctions execution completes
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `LOKKI_BATCH_JOB_QUEUE` | Override batch job queue |
| `LOKKI_BATCH_JOB_DEFINITION` | Override batch job definition |

### Packaging

Both Lambda and Batch handlers need to be included in deployment packages. The Lambda package includes:
- `lokki/runtime/handler.py` - Lambda handler
- `lokki/runtime/batch.py` - Batch handler  
- `lokki/runtime/batch_main.py` - Batch entry point
