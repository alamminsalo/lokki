# lokki — Implementation Tasks

Tasks are grouped by milestone. Each milestone should be completable and testable independently. Dependencies between tasks are noted where relevant.

---

## Milestone 1 — Project Scaffolding

**T1.1** Initialise the project with `uv init`, configure `pyproject.toml` with package metadata and dependencies (`boto3`, `stepfunctions`, `pyyaml`).

**T1.2** Create the full directory skeleton as defined in the design:
```
lokki/
├── __init__.py
├── decorators.py
├── graph.py
├── runner.py
├── s3.py
├── config.py
├── builder/
│   ├── __init__.py
│   ├── builder.py
│   ├── lambda_pkg.py
│   ├── state_machine.py
│   └── cloudformation.py
└── runtime/
    ├── __init__.py
    └── handler.py
```

**T1.3** Write `lokki/__init__.py` exporting the public API: `flow`, `step`, `main`.

---

## Milestone 2 — Configuration (`lokki/config.py`)

**T2.1** Implement `_load_yaml(path)` — loads a YAML file, returns empty dict if file does not exist.

**T2.2** Implement `_deep_merge(base, override)` — recursively merges two dicts; scalars and lists in `override` replace those in `base`; nested dicts are merged recursively.

**T2.3** Implement `LokkiConfig`, `RolesConfig`, and `LambdaDefaultsConfig` dataclasses with all fields and defaults as per design section 13.

**T2.4** Implement `load_config()` — loads global (`~/.lokki/lokki.yml`) then local (`./lokki.yml`), deep-merges them, applies environment variable overrides (`LOKKI_ARTIFACT_BUCKET`, `LOKKI_ECR_REPO_PREFIX`, `LOKKI_BUILD_DIR`), returns a populated `LokkiConfig`.

**T2.5** Write unit tests for `_deep_merge` covering: scalar override, list replacement, nested dict merge, missing keys in either file, neither file present.

---

## Milestone 3 — Decorator & Graph Model

_Depends on: M1_

**T3.1** Implement `StepNode` class in `decorators.py`:
- `__init__(fn)` — stores function, name, default args, next pointer
- `__call__(*args, **kwargs)` — records default args, returns `self`
- `map(step_node)` — creates and returns a `MapBlock`
- `agg(step_node)` — raises `TypeError` (must be called on `MapBlock`)

**T3.2** Implement `MapBlock` class in `decorators.py`:
- `__init__(source, inner_head)` — stores source step and inner chain head/tail
- `map(step_node)` — appends step to the inner chain, returns `self`
- `agg(step_node)` — closes the block, attaches aggregation step, returns the `StepNode`

**T3.3** Implement `step` decorator function — wraps `fn` in a `StepNode` and returns it.

**T3.4** Implement `FlowGraph` in `graph.py`:
- `__init__(name, head)` — stores name, calls `_resolve(head)`
- `_resolve(head)` — walks the chain and populates `self.entries` as an ordered list of `TaskEntry | MapOpenEntry | MapCloseEntry`

**T3.5** Implement `flow` decorator function — wraps `fn` so calling it invokes the body, collects the returned chain, and returns a `FlowGraph` with `name` derived from `fn.__name__`.

**T3.6** Write unit tests for the decorator and graph covering: single task, linear chain, `.map().agg()`, chaining after `.agg()`, calling `.agg()` directly on a `StepNode` raises `TypeError`, flow name derivation from function name.

---

## Milestone 4 — CLI Entry Point

_Depends on: M3_

**T4.1** Implement `main(flow_fn)` in `lokki/__init__.py` (or a dedicated `cli.py`):
- Parses `sys.argv[1]`
- `build` → resolves `FlowGraph`, calls `Builder.build(graph, config)`
- `run` → resolves `FlowGraph`, calls `LocalRunner.run(graph)`
- Anything else → prints usage and exits with code 1

**T4.2** Ensure the `@flow` decorator arranges for `main` to be callable from `if __name__ == "__main__"` — either by injecting the guard automatically or documenting the manual pattern clearly.

---

## Milestone 5 — S3 & Serialisation Layer (`lokki/s3.py`)

_Depends on: M1_

**T5.1** Implement `write(bucket, key, obj) -> str` — serialises `obj` with `pickle.dumps` at `HIGHEST_PROTOCOL`, compresses with `gzip.compress`, uploads via `boto3`, returns the `s3://bucket/key` URL.

**T5.2** Implement `read(url) -> Any` — parses the S3 URL, downloads the object via `boto3`, decompresses and unpickles, returns the Python object.

**T5.3** Implement `_parse_url(url) -> (bucket, key)` — splits an `s3://` URL into bucket and key components.

**T5.4** Write unit tests using `moto` (or `unittest.mock`) to mock S3: round-trip write then read, URL parsing, error on malformed URL.

---

## Milestone 6 — Local Runner (`lokki/runner.py`)

_Depends on: M3, M5_

**T6.1** Implement `LocalStore` — mirrors the `s3.py` interface (`read`, `write`) but stores gzip-pickled files under a local temp directory keyed by step name and index.

**T6.2** Implement `LocalRunner.run(graph)`:
- Creates a `LocalStore` in a temp directory
- Iterates `graph.entries`
- `TaskEntry` → calls step function with resolved inputs from store, writes output to store
- `MapOpenEntry` → fans out using `ThreadPoolExecutor`, running the inner step chain for each item in the source step's output list; writes per-item results to store
- `MapCloseEntry` → collects all per-item results, passes as list to aggregation function, writes output to store

**T6.3** Write integration tests running the full birds example locally, asserting the final output equals `"flappy goose, flappy duck, flappy seagul"`.

---

## Milestone 7 — Runtime Handler (`lokki/runtime/handler.py`)

_Depends on: M5_

**T7.1** Implement `make_handler(fn) -> lambda_handler`:
- Reads `LOKKI_ARTIFACT_BUCKET` and `LOKKI_FLOW_NAME` from environment via `load_config()`
- Reads `run_id` from the event
- Resolves inputs: no upstream (first step) → passes event kwargs matching function signature; `result_url` present → downloads single object; `result_urls` present → downloads list and passes as single list arg
- Calls `fn` with resolved inputs
- Writes result to S3 at `lokki/<flow_name>/<run_id>/<step_name>/output.pkl.gz`
- If result is a list and step is a map source, also writes a map manifest JSON to `lokki/<flow_name>/<run_id>/<step_name>/map_manifest.json`
- Returns `{"result_url": "...", "run_id": "..."}` or `{"map_manifest_key": "...", "run_id": "..."}` for map sources

**T7.2** Write unit tests for `make_handler` covering: first step with no input, first step with event overrides, single input via `result_url`, list input via `result_urls`, map source writing manifest.

---

## Milestone 8 — Lambda Packaging (`lokki/builder/lambda_pkg.py`)

_Depends on: M3, M2_

**T8.1** Implement `generate_lambda_dir(step_node, graph, config, build_dir)`:
- Creates `<build_dir>/lambdas/<step_name>/` directory
- Writes the `Dockerfile` (multi-stage, using AWS Lambda Python base image, installing deps from `pyproject.toml` via `uv`, copying `lokki/` source and the generated `handler.py`)
- Writes the auto-generated `handler.py` that imports the user's step function and binds it to `make_handler`

**T8.2** Implement Dockerfile template as a string constant or Jinja2-style template, parameterised on the Python base image tag from `lambda_defaults.image_tag`.

**T8.3** Write tests asserting the generated `Dockerfile` contains the expected `FROM`, `COPY`, `RUN uv pip install`, and `CMD` lines; and that `handler.py` imports the correct function name.

---

## Milestone 9 — State Machine Generation (`lokki/builder/state_machine.py`)

_Depends on: M3, M2_

**T9.1** Implement `build_state_machine(graph, config) -> dict` — returns a valid Amazon States Language dict.

**T9.2** Implement `_task_state(step_node, config) -> dict` — generates a `Task` state invoking the step's Lambda ARN (constructed from `ecr_repo_prefix`, flow name, and step name), with `ResultPath` passing only the S3 result URL.

**T9.3** Implement `_map_state(map_open_entry, config) -> dict` — generates a `Map` state in `DISTRIBUTED` mode with:
- `ItemReader` pointing to the map manifest JSON in S3
- `ItemProcessor` containing the inner step chain as a nested state machine
- `ResultWriter` writing collected results back to S3

**T9.4** Implement the linear chaining of states using `Next` and `End` fields, ensuring correct ordering from `graph.entries`.

**T9.5** Write unit tests asserting the birds example produces a state machine with: a `GetBirds` Task state, a `Map` state containing `FlapBird`, and a `JoinBirds` Task state; correct `Next` pointers; and `"End": true` on the final state.

---

## Milestone 10 — CloudFormation Generation (`lokki/builder/cloudformation.py`)

_Depends on: M9, M2_

**T10.1** Implement `build_template(graph, config) -> str` — returns a valid CloudFormation YAML string.

**T10.2** Implement Lambda function resource generation (one per step) with: `PackageType: Image`, `ImageUri` referencing ECR, `Role` from `config.roles.lambda_`, `Timeout` and `MemorySize` from `lambda_defaults`, environment variables from `lambda_env` plus `LOKKI_ARTIFACT_BUCKET` and `LOKKI_FLOW_NAME`.

**T10.3** Implement IAM role resources: `LambdaExecutionRole` (S3 read/write on lokki prefix, CloudWatch Logs) and `StepFunctionsExecutionRole` (Lambda invoke, S3 read/write for Distributed Map result writing). Use ARNs from `config.roles` if provided, otherwise generate the role resources.

**T10.4** Implement the Step Functions state machine resource with the state machine JSON inlined via `DefinitionString` and `!Sub` for Lambda ARN interpolation.

**T10.5** Implement the Parameters block (`FlowName`, `S3Bucket`, `ECRRepoPrefix`, `ImageTag`).

**T10.6** Write tests asserting the generated YAML is valid (`yaml.safe_load` parses without error) and contains expected resource logical IDs for each step.

---

## Milestone 11 — Build Orchestrator (`lokki/builder/builder.py`)

_Depends on: M8, M9, M10_

**T11.1** Implement `Builder.build(graph, config)`:
- Creates `<config.build_dir>/` output directory
- Calls `generate_lambda_dir` for each step node in `graph.nodes`
- Calls `build_state_machine` and writes output to `<build_dir>/statemachine.json`
- Calls `build_template` and writes output to `<build_dir>/template.yaml`
- Prints a summary of generated files

**T11.2** Write an integration test running `build` on the birds example and asserting all expected files exist in the output directory with non-empty content.

---

## Milestone 12 — End-to-End & Hardening

**T12.1** Write a full end-to-end local run test from CLI invocation (`python birds_flow_example.py run`) asserting the final printed or returned output.

**T12.2** Write a full build test from CLI invocation (`python birds_flow_example.py build`) asserting all artifacts are generated.

**T12.3** Add clear error messages for common user mistakes: missing `artifact_bucket` in config, `@flow` function not returning a chain, `.agg()` called without a preceding `.map()`.

**T12.4** Add a `--help` flag to the CLI that prints available commands and a short description.

**T12.5** Write a `README.md` covering: installation, quickstart with the birds example, `lokki.yml` configuration reference, `build` and `run` commands, and deploying the CloudFormation stack.
