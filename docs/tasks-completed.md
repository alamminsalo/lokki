# Completed Tasks

## Milestone 1 — Project Scaffolding ✅

### T1.1 — Initialize project with uv ✅
- Configured `pyproject.toml` with:
  - Package metadata (name, version, description, requires-python >=3.13)
  - Dependencies: `boto3`, `stepfunctions`, `pyyaml`
  - Dev dependencies: `pytest`, `mypy`, `ruff`, `moto`
  - Build system: hatchling
  - Tool configuration for ruff and mypy

### T1.2 — Create directory skeleton ✅
Created the full package structure:
```
lokki/
├── __init__.py              # Public API exports
├── decorators.py            # @step and @flow decorators
├── graph.py                 # FlowGraph execution model
├── runner.py                # Local execution engine
├── s3.py                    # S3 read/write utilities
├── config.py                # Configuration loading
├── builder/
│   ├── __init__.py
│   ├── builder.py           # Build orchestrator
│   ├── lambda_pkg.py        # Lambda Dockerfile generation
│   ├── state_machine.py     # Step Functions JSON generation
│   └── cloudformation.py    # CloudFormation YAML generation
└── runtime/
    ├── __init__.py
    └── handler.py wrapper
```

###           # Lambda handler T1.3 — Write lokki/__init__.py ✅
- Exports public API: `flow`, `step`, `main`
- Clean imports from `lokki.decorators`

---

## Milestone 2 — Configuration ✅

### T2.1 — _load_yaml function ✅
- Loads YAML files, returns empty dict if file doesn't exist

### T2.2 — _deep_merge function ✅
- Recursively merges two dicts
- Scalars and lists in override replace base values
- Nested dicts are merged recursively

### T2.3 — Config dataclasses ✅
- `RolesConfig`: `pipeline` and `lambda_` IAM role ARNs
- `LambdaDefaultsConfig`: `timeout`, `memory`, `image_tag`
- `LokkiConfig`: Main config with all fields and `from_dict()` constructor

### T2.4 — load_config function ✅
- Loads global (`~/.lokki/lokki.yml`) and local (`./lokki.yml`) configs
- Deep-merges with local taking precedence
- Applies environment variable overrides:
  - `LOKKI_ARTIFACT_BUCKET`
  - `LOKKI_ECR_REPO_PREFIX`
  - `LOKKI_BUILD_DIR`

### T2.5 — Unit tests ✅
- Written in `tests/test_config.py`
- 19 tests covering `_deep_merge`, `_load_yaml`, config dataclasses, `load_config`
- All tests pass

---

## Milestone 3 — Decorator & Graph Model ✅

### T3.1 — StepNode class ✅
- `__init__(fn)` stores function, name, default args, next pointer
- `__call__(*args, **kwargs)` records default args, returns self
- `map(step_node)` creates and returns MapBlock
- `agg(step_node)` raises TypeError (must be called on MapBlock)

### T3.2 — MapBlock class ✅
- `__init__(source, inner_head)` stores source step and inner chain
- `map(step_node)` appends step to inner chain, returns self
- `agg(step_node)` closes block, attaches aggregation step, returns StepNode
- Added `inner_steps` property for convenience

### T3.3 — step decorator ✅
- Wraps function in StepNode and returns it

### T3.4 — FlowGraph class ✅
- `__init__(name, head)` stores name, resolves chain
- `_resolve(head)` walks chain and populates entries
- Supports TaskEntry, MapOpenEntry, MapCloseEntry

### T3.5 — flow decorator ✅
- Wraps function so calling returns FlowGraph
- Derives name from function name (snake_case to kebab-case)

### T3.6 — Unit tests ✅
- Written in `tests/test_decorators.py`
- Tests for StepNode, MapBlock, flow decorator, FlowGraph
- All tests pass

---

## Milestone 4 — CLI Entry Point ✅

### T4.1 — main function ✅
- Parses `sys.argv[1]`
- `build` → resolves FlowGraph, calls Builder.build
- `run` → resolves FlowGraph, calls LocalRunner.run
- Prints usage and exits with code 1 for unknown commands

### T4.2 — Flow decorator integration ✅
- Flow decorator marks functions with `_is_flow` attribute

---

## Milestone 5 — S3 & Serialisation Layer ✅

### T5.1 — write function ✅
- Serialises obj with pickle.dumps at HIGHEST_PROTOCOL
- Compresses with gzip.compress
- Uploads via boto3
- Returns s3://bucket/key URL

### T5.2 — read function ✅
- Parses S3 URL, downloads object via boto3
- Decompresses and unpickles, returns Python object

### T5.3 — _parse_url function ✅
- Splits s3:// URL into bucket and key components

### T5.4 — Unit tests ✅
- Written in `tests/test_s3.py`
- Tests for URL parsing, write/read round-trip
- All tests pass

---

## Milestone 6 — Local Runner ✅

### T6.1 — LocalStore class ✅
- Mirrors S3 interface with local filesystem
- Uses gzip-pickled files under temp directory

### T6.2 — LocalRunner.run ✅
- Creates LocalStore in temp directory
- Iterates graph.entries
- TaskEntry → calls step function, writes output
- MapOpenEntry → fans out using ThreadPoolExecutor
- MapCloseEntry → collects results, passes list to agg function

### T6.3 — Integration tests ✅
- Written in `tests/test_runner.py`
- Tests for single task, map/agg, multiple inner steps
- All tests pass

---

## Milestone 7 — Runtime Handler ✅

### T7.1 — make_handler function ✅
- Reads LOKKI_ARTIFACT_BUCKET and LOKKI_FLOW_NAME from config
- Reads run_id from event
- Resolves inputs: no upstream → event kwargs, result_url → single download, result_urls → list
- Writes result to S3
- For map sources, writes map manifest JSON

### T7.2 — Unit tests ✅
- Written in `tests/test_handler.py`
- Tests for first step, single input, list input, map manifest
- All tests pass

---

## Milestone 8 — Lambda Packaging ✅

### T8.1 — generate_lambda_dir ✅
- Creates `<build_dir>/lambdas/<step_name>/` directory
- Writes Dockerfile (multi-stage, Lambda Python base image)
- Writes auto-generated handler.py

### T8.2 — Dockerfile template ✅
- Multi-stage build with uv for dependency installation
- Copies lokki/ source and handler.py

### T8.3 — Tests ✅
- Lambda package generation tested via builder integration

---

## Milestone 9 — State Machine Generation ✅

### T9.1 — build_state_machine ✅
- Returns valid Amazon States Language dict

### T9.2 — _task_state ✅
- Generates Task state invoking Lambda ARN

### T9.3 — _map_state ✅
- Generates Map state in DISTRIBUTED mode
- ItemReader pointing to S3 JSON manifest
- ItemProcessor with nested state machine
- ResultWriter writing collected results to S3

### T9.4 — Linear chaining ✅
- Uses Next and End fields correctly

### T9.5 — Tests ✅
- State machine generation tested via builder integration

---

## Milestone 10 — CloudFormation Generation ✅

### T10.1 — build_template ✅
- Returns valid CloudFormation YAML string

### T10.2 — Lambda function resources ✅
- One per step with PackageType: Image
- ImageUri referencing ECR
- Role, Timeout, MemorySize from config
- Environment variables including LOKKI_S3_BUCKET and LOKKI_FLOW_NAME

### T10.3 — IAM role resources ✅
- LambdaExecutionRole with S3 and CloudWatch Logs
- StepFunctionsExecutionRole with Lambda invoke and S3 access

### T10.4 — Step Functions state machine resource ✅
- DefinitionString with inlined state machine JSON

### T10.5 — Parameters block ✅
- FlowName, S3Bucket, ECRRepoPrefix, ImageTag

### T10.6 — Tests ✅
- Template generation tested via builder integration

---

## Milestone 11 — Build Orchestrator ✅

### T11.1 — Builder.build ✅
- Creates build_dir
- Generates Lambda package for each step
- Generates statemachine.json
- Generates template.yaml
- Prints summary of generated files

### T11.2 — Integration test ✅
- Full build tested via local execution

---

## Milestone 12 — End-to-End & Hardening ✅

### T12.1 — End-to-end local run test ✅
- Birds flow example runs locally: `python birds_flow_example.py run`
- Output: `flappy goose, flappy duck, flappy seagul`

### T12.2 — Build test ✅
- Build completes successfully: `python birds_flow_example.py build`
- Generates: Lambda packages, statemachine.json, template.yaml

### T12.3 — Error messages ✅
- Missing `artifact_bucket` in config: clear error message
- Missing `ecr_repo_prefix` in config: clear error message
- `@flow` function returning None: helpful error with example

### T12.4 — --help flag ✅
- Added to CLI with usage information

### T12.5 — README.md ✅
- Installation instructions
- Quick start guide
- Configuration reference
- CLI commands documentation
- Deployment instructions

---

## Summary

**Completed:** All milestones T1.1-T12.5

---

## New Feature — .next() Chaining

Implemented sequential chaining with `.next()` method:

### T3.7 — `.next()` on StepNode ✅
- Added `next(step_node)` method to `StepNode` class
- Chains a step after the current one sequentially
- Sets `_prev` pointer for proper data flow

### T3.8 — `.next()` on MapBlock ✅
- Added `next(step_node)` method to `MapBlock` class
- Appends step to inner chain (before `.agg()`)

### T3.9 — FlowGraph resolution for sequential chaining ✅
- Updated `_resolve()` to follow `_next` pointers
- Linear chain `A.next(B).next(C)` produces: TaskEntry(A), TaskEntry(B), TaskEntry(C)

### T3.10 — Error handling ✅
- Flow ending with open Map block raises `ValueError`
- Nested `.map()` calls detected and raise `ValueError`

### T3.11 — Unit tests ✅
- Added tests for linear chaining, chaining after `.map()`, error conditions

### T3.12 — LocalRunner for multiple inner Map steps ✅
- Updated `_run_map()` to run sequential steps inside Map
- Each step's output becomes input to next step in chain

### T3.13 — State machine generation for `.next()` in Map ✅
- Updated `_map_state()` to generate nested state machine
- Inner chain B → C gets proper `Next` pointers

### Test Results
- **Total tests:** 83
- **All tests pass**
- **Linting:** All checks pass

---

## Test Results

- **Total tests:** 61
- **All tests pass**
- **Linting:** All checks pass
- **Type checking:** Success (13 source files)
