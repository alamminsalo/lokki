# lokki — Design Document

## Table of Contents

1. [Repository Layout](#1-repository-layout)
2. [Library Architecture](#2-library-architecture)
3. [Decorator Design](#3-decorator-design)
4. [Execution Graph](#4-execution-graph)
5. [CLI Entry Point](#5-cli-entry-point)
6. [Local Runner](#6-local-runner)
7. [Build Pipeline](#7-build-pipeline)
8. [S3 & Serialisation Layer](#8-s3--serialisation-layer)
9. [State Machine Generation](#9-state-machine-generation)
10. [CloudFormation Template Generation](#10-cloudformation-template-generation)
11. [Lambda Packaging](#11-lambda-packaging)
12. [Runtime Wrapper (Lambda Handler)](#12-runtime-wrapper-lambda-handler)
13. [Configuration](#13-configuration)
14. [Data Flow Walkthrough](#14-data-flow-walkthrough)

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

class StepNode:
    def __init__(self, fn):
        self.fn = fn
        self.name = fn.__name__
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


def step(fn):
    node = StepNode(fn)
    return node
```

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

Each flow script calls `lokki.main()` at the bottom (injected by the `@flow` decorator or added explicitly by the user):

```python
# at bottom of flow_script.py — auto-injected or written manually
if __name__ == "__main__":
    from lokki import main
    main(birds_flow)
```

`main()` inspects `sys.argv[1]` and dispatches:

| `sys.argv[1]` | Action |
|---|---|
| `build` | Instantiate `FlowGraph`, call `Builder.build(graph)` |
| `run` | Instantiate `FlowGraph`, call `LocalRunner.run(graph)` |
| _(anything else)_ | Print usage and exit |

The flow function is called with no arguments (or default arguments) to produce the `FlowGraph`. Any arguments can be overridden at deploy-time via the Step Functions input JSON — the `main()` CLI does not need to accept arguments because local `run` uses the defaults defined in the flow body.

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
└── template.yaml
```

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

States are named after the Python function: `GetBirds`, `FlapBird`, `JoinBirds` (PascalCase). The `stepfunctions` pip package is used as a helper for constructing and validating the state machine definition.

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
```

**IAM**

- `LambdaExecutionRole`: allows `logs:*`, `s3:GetObject`, `s3:PutObject` on the lokki prefix.
- `StepFunctionsExecutionRole`: allows `lambda:InvokeFunction` on all step Lambdas, `s3:GetObject` / `s3:PutObject` for Distributed Map result writing, `states:StartExecution` for nested executions (if needed).

**Lambda Functions** (one per `@step`)

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
def make_handler(fn: Callable) -> Callable:
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

---

## 13. Configuration

`lokki/config.py` is responsible for loading, merging, and exposing configuration to the rest of the library. Configuration is sourced from two `lokki.yml` files and environment variables, resolved in this order (highest precedence first):

```
environment variables → local lokki.yml → global ~/.lokki/lokki.yml → built-in defaults
```

### Loading & merging

```python
# lokki/config.py (simplified)
import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field

GLOBAL_CONFIG_PATH = Path.home() / ".lokki" / "lokki.yml"
LOCAL_CONFIG_PATH = Path.cwd() / "lokki.yml"

def _load_yaml(path: Path) -> dict:
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
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
    global_cfg = _load_yaml(GLOBAL_CONFIG_PATH)
    local_cfg  = _load_yaml(LOCAL_CONFIG_PATH)
    merged     = _deep_merge(global_cfg, local_cfg)
    return LokkiConfig.from_dict(merged)
```

### Config schema

```python
@dataclass
class RolesConfig:
    pipeline: str = ""   # IAM role ARN for Step Functions
    lambda_: str  = ""   # IAM role ARN for Lambda execution

@dataclass
class LambdaDefaultsConfig:
    timeout:   int = 900
    memory:    int = 512
    image_tag: str = "latest"

@dataclass
class LokkiConfig:
    artifact_bucket:  str = ""
    ecr_repo_prefix:  str = ""
    build_dir:        str = "lokki-build"
    roles:            RolesConfig          = field(default_factory=RolesConfig)
    lambda_env:       dict[str, str]       = field(default_factory=dict)
    lambda_defaults:  LambdaDefaultsConfig = field(default_factory=LambdaDefaultsConfig)

    @classmethod
    def from_dict(cls, d: dict) -> "LokkiConfig": ...
```

### Environment variable overrides

After loading and merging the YAML files, specific fields can be overridden by environment variables. This is primarily useful inside Lambda functions at runtime, where the full `lokki.yml` is not available.

| Environment variable | Overrides field |
|---|---|
| `LOKKI_ARTIFACT_BUCKET` | `artifact_bucket` |
| `LOKKI_ECR_REPO_PREFIX` | `ecr_repo_prefix` |
| `LOKKI_BUILD_DIR` | `build_dir` |

### Usage at build time vs runtime

At **build time** (`python flow_script.py build`), `load_config()` reads both YAML files from the filesystem and uses the merged result to populate the CloudFormation template and Dockerfiles (e.g. IAM role ARNs, ECR prefix, artifact bucket name). The flow name is derived directly from the `@flow`-decorated function name (e.g. `birds_flow` → `"birds-flow"`, lowercased and underscores replaced with hyphens) and is not configurable — it is baked into the CloudFormation resource names and S3 key prefixes at build time.

At **Lambda runtime**, the YAML files are not present. The Lambda functions receive their configuration entirely through environment variables injected by CloudFormation at deploy time — `LOKKI_ARTIFACT_BUCKET`, `LOKKI_FLOW_NAME` (set to the derived flow name), and any entries from `lambda_env` in the config.

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
