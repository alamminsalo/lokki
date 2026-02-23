# lokki — Implementation Tasks

Tasks are grouped by milestone. Each milestone should be completable and testable independently. Dependencies between tasks are noted where relevant.

---

## Milestone 1 — Project Scaffolding

**T1.1** Initialise the project with `uv init`, configure `pyproject.toml` with package metadata and dependencies (`boto3`).

**T1.2** Create the full directory skeleton as defined in the design:
```
lokki/
├── __init__.py
├── decorators.py
├── graph.py
├── runner.py
├── config.py
├── _aws.py
├── _utils.py
├── _errors.py
├── logging.py
├── store/
│   ├── __init__.py
│   ├── protocol.py
│   ├── local.py
│   └── s3.py
├── builder/
│   ├── __init__.py
│   ├── builder.py
│   ├── lambda_pkg.py
│   ├── state_machine.py
│   └── cloudformation.py
└── runtime/
    ├── __init__.py
    ├── handler.py
    ├── batch.py
    └── batch_main.py
```

**T1.3** Write `lokki/__init__.py` exporting the public API: `flow`, `step`, `main`.

---

## Milestone 2 — Configuration (`lokki/config.py`)

**T2.1** Implement `_load_toml(path)` — loads a TOML file, returns empty dict if file does not exist. Uses Python's stdlib `tomllib` (requires Python 3.11+).

**T2.2** Implement `_deep_merge(base, override)` — recursively merges two dicts; scalars and lists in `override` replace those in `base`; nested dicts are merged recursively.

**T2.3** Implement `LokkiConfig`, `AwsConfig`, `RolesConfig`, `LambdaConfig`, and `LoggingConfig` dataclasses with all fields and defaults as per the new config schema:
- `aws.artifact_bucket`, `aws.ecr_repo_prefix`, `aws.roles`
- `lambda.timeout`, `lambda.memory`, `lambda.image_tag`, `lambda.env`
- `build_dir`, `logging`

**T2.4** Implement `load_config()` — loads global (`~/.lokki/lokki.toml`) then local (`./lokki.toml`), deep-merges them, applies environment variable overrides (`LOKKI_ARTIFACT_BUCKET`, `LOKKI_ECR_REPO_PREFIX`, `LOKKI_BUILD_DIR`), returns a populated `LokkiConfig`.

**T2.5** Write unit tests for `_deep_merge` covering: scalar override, list replacement, nested dict merge, missing keys in either file, neither file present.

### T2.6 — Update config schema for new format

Update `LokkiConfig` to use the new nested structure:
- Move `artifact_bucket`, `ecr_repo_prefix`, `roles` under `aws`
- Move `lambda_defaults` to `lambda` with `timeout`, `memory`, `image_tag`
- Move `lambda_env` to `lambda.env`
- Add `logging` config

### T2.7 — Update config loading for new format

Update `load_config()` to handle the new TOML structure with nested `aws` and `lambda` sections. Ensure backward compatibility or provide migration guidance.

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

### T3.7 — Implement `.next()` method on StepNode

- Add `next(step_node)` method to `StepNode` class in `decorators.py`
- Chains a step after the current one without parallelism
- Returns the next `StepNode` to allow further chaining
- Sets internal `_next` pointer to the new step

### T3.8 — Implement `.next()` method on MapBlock

- Add `next(step_node)` method to `MapBlock` class
- Appends step to the inner chain (before `.agg()`)
- Returns the added `StepNode` to allow further chaining
- Allows chaining multiple steps inside a Map block: `A.map(B).next(C).next(D).agg(E)`

### T3.9 — Update FlowGraph resolution for sequential chaining

- Update `_resolve(head)` in `graph.py` to handle `._next` pointers
- Collect sequential steps into the entries list in order
- Linear chain `A.next(B).next(C)` should produce: `TaskEntry(A)`, `TaskEntry(B)`, `TaskEntry(C)`

### T3.10 — Add error handling for invalid flows

- Flow ending with an open Map block (without `.agg()`) must raise `ValueError`
- Nested `.map()` calls (Map inside Map) should raise `ValueError`
- Add validation in `FlowGraph._resolve()` before returning entries

### T3.11 — Update unit tests for `.next()`

- Add tests for linear chaining: `A.next(B).next(C)`
- Add tests for chaining after `.map()`: `A.map(B).next(C).agg(D)`
- Add tests for error conditions: open Map block, nested `.map()`

### T3.12 — Update LocalRunner for multiple inner Map steps

- Update `_run_map()` to handle multiple sequential steps inside a Map block
- Inner chain `B.next(C).next(D)` should run B, then C, then D for each item
- Pass output of each inner step as input to the next

### T3.13 — Update state machine generation for `.next()` in Map

- Update `state_machine.py` to generate nested state machine for inner chain
- `Map(B.next(C))` should generate nested states: B → C with proper `Next` chaining
- Ensure aggregation step receives collected results from the final inner step

---

## Milestone 4 — CLI Entry Point

_Depends on: M3_

**T4.1** Implement `main(flow_fn)` in `lokki/__init__.py` (or a dedicated `cli.py`):
- Parses `sys.argv[1]`
- `build` → resolves `FlowGraph`, calls `Builder.build(graph, config)`
- `run` → resolves `FlowGraph`, calls `LocalRunner.run(graph)`
- Anything else → prints usage and exits with code 1

**T4.2** The `@flow` decorator is combined with an explicit `main(flow_fn)` call in the `if __name__ == "__main__"` block. Users add `main(my_flow)` at the bottom of their script.

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

**T8.1** Implement `generate_shared_lambda_files(graph, config, build_dir)`:
- Creates `<build_dir>/lambdas/` directory (shared, not per-step)
- Writes the shared `Dockerfile` (multi-stage, using AWS Lambda Python base image, installing deps from user's `pyproject.toml` via `uv`, copying the generated `handler.py`)
- Writes the auto-generated `handler.py` that dynamically imports the step function based on `LOKKI_STEP_NAME` and `LOKKI_MODULE_NAME` environment variables

**T8.2** Implement shared Dockerfile template:
- Single template for all steps (not per-step)
- Parameterised on the Python base image tag from `lambda.image_tag`
- Installs dependencies from user's `pyproject.toml` (which must include `lokki`)

**T8.3** Write tests asserting the generated `Dockerfile` contains the expected `FROM`, `COPY`, `RUN uv pip install`, and `CMD` lines; and that `handler.py` reads `LOKKI_STEP_NAME` and `LOKKI_MODULE_NAME` env vars.

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

**T10.2** Implement Lambda function resource generation (one per step) with: `PackageType: Image`, `ImageUri` referencing ECR, `Role` from `config.aws.roles.lambda_`, `Timeout` and `MemorySize` from `lambda`, environment variables from `lambda.env` plus `LOKKI_ARTIFACT_BUCKET` and `LOKKI_FLOW_NAME`.

**T10.3** Implement IAM role resources: `LambdaExecutionRole` (S3 read/write on lokki prefix, CloudWatch Logs) and `StepFunctionsExecutionRole` (Lambda invoke, S3 read/write for Distributed Map result writing). Use ARNs from `config.aws.roles` if provided, otherwise generate the role resources.

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

**T12.5** Write a `README.md` covering: installation, quickstart with the birds example, `lokki.toml` configuration reference, `build` and `run` commands, and deploying the CloudFormation stack.

---

## Milestone 13 — Logging & Observability

_Depends on: M2, M6_

**T13.1** Implement `LoggingConfig` dataclass in `config.py`:
- `level`: str = "INFO" (DEBUG, INFO, WARNING, ERROR)
- `format`: str = "human" (human or json)
- `progress_interval`: int = 10
- `show_timestamps`: bool = True

Add environment variable override: `LOKKI_LOG_LEVEL`.

**T13.2** Implement `lokki/logging.py`:
- `get_logger(name, config)` factory function
- `StepLogger` class with `start()`, `complete(duration)`, `fail(duration, error)` methods
- `MapProgressLogger` class with `start(total_items)`, `update(status)`, `complete()` methods
- `HumanFormatter` and `JsonFormatter` classes

**T13.3** Implement human-readable formatter:
- Step start: `[INFO] Step 'step_name' started at 2024-01-15T10:30:00`
- Step complete: `[INFO] Step 'step_name' completed in 2.345s (status=success)`
- Step fail: `[ERROR] Step 'step_name' failed after 1.234s: ValueError: invalid input`
- Progress bar: `[=====>                    ] 30/100 (30%) completed`

**T13.4** Implement JSON formatter:
- Each log line is a JSON object with: level, ts, event, step, duration, status, message
- Example: `{"level": "INFO", "ts": "2024-01-15T10:30:00.123Z", "event": "step_start", "step": "get_data"}`

**T13.5** Integrate logging into `LocalRunner`:
- Wrap `_run_task()` with step start/complete/fail logging
- Wrap `_run_map()` with map progress tracking
- Wrap `_run_agg()` with step logging

**T13.6** Write unit tests for logging module:
- Test `StepLogger` output formats
- Test `MapProgressLogger` progress updates
- Test JSON formatter output
- Test configuration loading from lokki.toml

**T13.7** Integrate logging into Lambda runtime handler:
- Log function invocation
- Log input processing
- Log execution duration
- Log errors with stack traces

---

## Milestone 14 — Deploy Command

_Depends on: M11, M12_

**T14.1** Implement `lokki/deploy.py`:
- `Deployer` class with `__init__(stack_name, region, image_tag)`
- `deploy(graph, config)` method that orchestrates the full deploy
- `_validate_credentials()` - verify AWS credentials are configured
- `_push_images(ecr_prefix)` - build and push Docker images to ECR
- `_deploy_stack(config)` - deploy CloudFormation stack

**T14.2** Implement Docker image build and push:
- Build a single shared Docker image from `lokki-build/lambdas/Dockerfile`
- Tag image with `<ecr_repo_prefix>/lokki:<image_tag>`
- Push to ECR using `docker push`
- Handle Docker not installed error gracefully

**T14.2a** Update CloudFormation to use shared image with env vars:
- Each Lambda function references the same Docker image URI
- Use `PackageType: Image` with `ImageUri` pointing to shared image (`lokki:<image_tag>`)
- Pass `LOKKI_STEP_NAME` and `LOKKI_MODULE_NAME` environment variables per function
- Handler dispatches to correct step based on these env vars

**T14.2b** Support empty `ecr_repo_prefix` for local testing:
- When `aws.ecr_repo_prefix` is empty, skip ECR push entirely
- Use local Docker image names directly (`<step>:<image_tag>`)
- Update CloudFormation to use local image URIs when ECR prefix is empty
- Useful for LocalStack or local development testing

**T14.2c** Support `aws.endpoint` for local AWS services:
- Add `endpoint` field to `AwsConfig` (e.g., `http://localhost:4566` for LocalStack)
- Pass endpoint to boto3 clients in deploy.py and runtime handler
- When endpoint is set, configure boto3 to use it for S3, Lambda, Step Functions, CloudFormation, ECR
- Skip Docker login/push validation when using local endpoint

**T14.3** Implement CloudFormation deployment:
- Use boto3 to create or update stack
- Pass parameters: FlowName, S3Bucket, ECRRepoPrefix, ImageTag
- Wait for stack creation/update to complete
- Report stack status and output

**T14.4** Add `deploy` command to CLI:
- Parse `--stack-name`, `--region`, `--image-tag`, `--confirm` arguments
- Call `Deployer.deploy(graph, config)`
- Print success/failure messages

**T14.5** Add error handling:
- Docker not available: clear error message with installation instructions
- ECR authorization: prompt to run `aws ecr get-login-password`
- CloudFormation errors: display error and suggest fixes

**T14.6** Write integration tests:
- Test deploy with mocked AWS clients
- Test image build and push
- Test CloudFormation stack creation

---

## Milestone 15 — Local Testing with LocalStack

**Purpose**: Enable full pipeline testing locally using LocalStack and SAM CLI. This provides an AWS simulation environment that catches deployment and integration issues early.

### T15.1 — ZIP Package with Dispatcher Handler ✅

**Status**: COMPLETED

- Generate single `function.zip` containing all dependencies, lokki runtime, and flow module
- Create dispatcher `handler.py` that reads `LOKKI_STEP_NAME` env var to route to correct step
- Handle both `StepNode` and raw function objects

### T15.2 — SAM Template for Local Testing ✅

**Status**: COMPLETED

- Generate `sam.yaml` alongside `template.yaml`
- Use `CodeUri: lambdas/function.zip` for Lambda functions
- Use single `Handler: handler.lambda_handler` for all functions
- Set `LOKKI_AWS_ENDPOINT` for SAM local invoke connectivity
- Set `LOKKI_S3_BUCKET` and `LOKKI_FLOW_NAME` env vars

### T15.3 — CloudFormation ZIP Support ✅

**Status**: COMPLETED

- Add `PackageType: ZipFile` support in CloudFormation template
- Add explicit `Handler` property for ZIP packages
- Remove inline `ZipFile` handler (use shared handler)

### T15.4 — S3 Endpoint Configuration ✅

**Status**: COMPLETED

- Add `set_endpoint()` function to lokki S3 module
- Configure endpoint globally for all S3 operations
- Support for LocalStack S3 endpoint

### T15.5 — Runtime Handler Endpoint Support ✅

**Status**: COMPLETED

- Read `LOKKI_AWS_ENDPOINT` from environment
- Configure S3 client with endpoint for Lambda runtime
- Write manifest using configured endpoint

### T15.6 — Deploy to LocalStack ✅

**Status**: COMPLETED

- Detect LocalStack via `aws.endpoint` configuration
- Use AWS CLI with `--endpoint-url` for LocalStack deployment
- Skip Docker image push for ZIP deployments
- Fall back to AWS CLI when `samlocal` is not available

### T15.7 — Build Integration ✅

**Status**: COMPLETED

- Generate both CloudFormation and SAM templates
- SAM template used for LocalStack deployments
- CloudFormation template used for real AWS

---

## Milestone 16 — Step Functions Local Deployment

**Purpose**: Deploy and test the full Step Functions state machine locally using LocalStack. This enables end-to-end pipeline testing without real AWS.

### T16.1 — SAM Template State Machine Resource ✅

**Status**: COMPLETED

- Add `AWS::Serverless::StateMachine` resource to `sam.yaml`
- Reference the generated `statemachine.json`
- Configure IAM role for state machine

### T16.2 — SAM Local Start-API ✅

**Status**: COMPLETED (N/A - not applicable)

- SAM CLI does not support local Step Functions API
- Use AWS CLI directly with LocalStack for Step Functions operations

### T16.3 — LocalStack Step Functions Support ✅

**Status**: COMPLETED

- Test state machine deployment to LocalStack via AWS CLI
- Step Functions resources deploy but require manual state machine creation
- Lambdas can be tested individually via `sam local invoke`

### T16.4 — Integration Test ✅

**Status**: COMPLETED

- Individual Lambda functions can be tested via `sam local invoke`
- Full pipeline requires manual Step Functions state machine creation via AWS CLI

### T16.5 — Dev Scripts ✅

**Status**: COMPLETED

- `dev/test-sam-local.sh` — Test individual Lambda functions
- `dev/deploy-localstack.sh` — Deploy full pipeline to LocalStack
- `dev/run-localstack.sh` — Run pipeline and verify results

---

## Milestone 17 — TOML Configuration Format

**Purpose**: Replace YAML configuration with TOML using Python stdlib. This removes the `pyyaml` dependency and leverages Python 3.11+'s built-in `tomllib` module.

### T17.1 — Update config file naming ✅

- Change default config filename from `lokki.yml` to `lokki.toml`
- Update `GLOBAL_CONFIG_PATH` from `~/.lokki/lokki.yml` to `~/.lokki/lokki.toml`
- Update `LOCAL_CONFIG_PATH` from `./lokki.yml` to `./lokki.toml`
- Add migration documentation for users upgrading from YAML config

### T17.2 — Update config loading ✅

- Replace `yaml.safe_load()` with `tomllib.load()` (requires opening file in binary mode `"rb"`)
- Update `_load_yaml()` to `_load_toml()` with proper error handling
- Ensure TOML tables (`[section]`) map correctly to nested dict structure

### T17.3 — Update configuration schema documentation ✅

- Change all YAML examples in docs to TOML format
- Update `pyproject.toml` dependencies to remove `pyyaml`
- Verify all existing configuration fields work with TOML syntax

### T17.4 — Environment variable handling ✅

- Ensure environment variable overrides still work with TOML config
- Test that `LOKKI_ARTIFACT_BUCKET`, `LOKKI_ECR_REPO_PREFIX`, `LOKKI_BUILD_DIR`, `LOKKI_LOG_LEVEL` override TOML values

### T17.5 — Backward compatibility (optional)

- Consider supporting both `lokki.yml` and `lokki.toml` with deprecation warning for YAML
- If supporting both: check for TOML first, then YAML, then defaults
- Document migration path for existing YAML users

### T17.6 — Update tests ✅

- Update existing config tests to use TOML fixtures
- Add tests for TOML-specific syntax (tables, inline tables, arrays)
- Ensure deep merge works correctly with TOML structure

### T17.7 — Update builder integration ✅

- Ensure builder code works with new config structure
- Update any hardcoded references to `lokki.yml`
- Update error messages to reference `lokki.toml`

### T17.8 — Update documentation ✅

- Update AGENTS.md config references
- Update README.md examples
- Add migration guide for YAML to TOML

### T17.9 — Remove stepfunctions dependency ✅

- Remove `stepfunctions` pip package from dependencies
- Update state machine generation to build ASL JSON directly as Python dict
- Remove any imports or references to `stepfunctions` package
- Update builder tests to not depend on stepfunctions package

---

## Milestone 18 — Test Coverage Improvements

**Purpose**: Improve test coverage for untested modules. Add `moto` for AWS mocking in tests.

### T18.1 — Add moto to dev dependencies ✅

- Add `moto>=5.0.0` to dev dependencies in `pyproject.toml`
- Update `tests/test_deploy.py` to use moto for AWS mocking

### T18.2 — Test graph.py ✅

- Create `tests/test_graph.py`
- Test `FlowGraph` construction with various chain structures
- Test `_find_chain_start` method
- Test `_resolve_from_head` method
- Test `_resolve_map_block` method
- Test `_validate` method (open map block detection)
- Test `TaskEntry`, `MapOpenEntry`, `MapCloseEntry` types

### T18.3 — Test state_machine.py ✅

- Create `tests/test_state_machine.py`
- Test `build_state_machine` function with simple chain
- Test task state generation with correct ARN
- Test Map block states (MapOpen, Map iterations, MapClose)
- Test state ordering and transitions
- Test various flow configurations

### T18.4 — Test cloudformation.py ✅

- Create `tests/test_cloudformation.py`
- Test `build_template` function
- Test IAM role generation
- Test Lambda function resources
- Test State Machine definition
- Test parameters handling
- Test ZIP package type support

### T18.5 — Test sam_template.py ✅

- Create `tests/test_sam_template.py`
- Test `build_sam_template` function
- Test ZIP package support
- Test environment variables in template

### T18.6 — Test builder.py ✅

- Create `tests/test_builder.py`
- Test full build flow
- Test directory creation
- Test file generation

### T18.7 — Test deploy.py ✅

- Create `tests/test_deploy.py`
- Test `Deployer` class initialization
- Test credential validation
- Test local image push
- Test stack deployment
- Test error handling

---

## Milestone 19 — CLI Commands: show, logs, destroy

_Purpose_: Implement AWS integration commands for viewing run status, fetching logs, and destroying stacks.

### T19.1 — Implement show command

- Add `show` subparser to CLI with options:
  - `--n COUNT` (default: 10) - number of runs to show
  - `--run RUN_ID` - show specific run ID
- Implement `show.py` module with `show_executions` function
- Use boto3 Step Functions client to list executions
- Parse and display execution status, start time, duration
- Support LocalStack endpoint if configured in config

### T19.2 — Implement logs command

- Add `logs` subparser to CLI with options:
  - `--start DATETIME` - ISO 8601 format (default: 1 hour ago)
  - `--end DATETIME` - ISO 8601 format (default: now)
  - `--run RUN_ID` - specific run ID
  - `--tail` - continuously poll logs
- Implement `logs.py` module with `fetch_logs` function
- Use boto3 CloudWatch Logs client to filter log events
- Query log groups: `/aws/lambda/{flow-name}-{step-name}`
- Support LocalStack endpoint if configured
- For `--tail`, poll every 2 seconds until interrupted

### T19.3 — Implement destroy command

- Add `destroy` subparser to CLI with option:
  - `--confirm` - skip confirmation prompt
- Implement `destroy.py` module with `destroy_stack` function
- Use boto3 CloudFormation client to delete stack
- Show confirmation prompt (unless `--confirm`)
- Wait for stack deletion to complete
- Handle stack not found errors gracefully
- Support LocalStack endpoint if configured

### T19.4 — Update CLI main function

- Add show, logs, destroy subparsers to main
- Parse options and dispatch to appropriate module
- Add error handling for AWS operations

### T19.5 — Unit tests for show

- Create `tests/test_show.py`
- Test execution listing with mocked boto3
- Test output formatting
- Test `--n` and `--run` options

### T19.6 — Unit tests for logs

- Create `tests/test_logs.py`
- Test log fetching with mocked boto3
- Test datetime parsing
- Test tail mode polling

### T19.7 — Unit tests for destroy

- Create `tests/test_destroy.py`
- Test stack deletion with mocked boto3
- Test confirmation prompt
- Test error handling

---

## Milestone 20 — Flow-level Parameters in `.next()`

_Purpose_: Allow passing flow-level parameters directly to steps via `.next(step, param=val)` without threading through intermediate steps.

### T20.1 — Update decorators.py

- Modify `StepNode.next()` to accept `**kwargs`
- Store flow kwargs on `StepNode._flow_kwargs` attribute
- Apply same changes to `MapBlock.next()`

### T20.2 — Update runner.py

- Modify `_run_task()` to handle flow kwargs
- Merge flow kwargs with step execution:
  - If previous result exists: `fn(result, **flow_kwargs)`
  - If no previous result: `fn(**flow_kwargs)`
- Test with various combinations

### T20.3 — Unit tests

- Create `tests/test_flow_kwargs.py`
- Test basic flow kwargs passing
- Test flow kwargs without previous step
- Test chaining with flow kwargs
- Test error handling for invalid kwargs

---

## Milestone 21 — Flow-level Parameters in `.map()` and `.agg()`

_Purpose_: Extend flow-level parameters support to `.map()` and `.agg()` methods.

### T21.1 — Update MapBlock decorators

- Modify `MapBlock.__init__()` to initialize `_flow_kwargs`
- Modify `MapBlock.map()` to accept `**kwargs` and store on inner step
- Modify `MapBlock.agg()` to accept `**kwargs` and store on aggregation step

### T21.2 — Update runner.py for map blocks

- Modify `_run_map()` to handle flow kwargs for mapped steps
- Modify `_run_agg()` to handle flow kwargs for aggregation step

### T21.3 — Unit tests

- Test flow kwargs with `.map()`
- Test flow kwargs with `.agg()`
- Test combined usage with `.map().agg()`
- Test error handling

---

## Milestone 22 — Validate Nested .map() Blocks

_Purpose_: Detect and report nested `.map()` blocks which are not supported.

### T22.1 — Update graph.py validation

- In `FlowGraph._validate()`, detect when a MapBlock is opened inside another MapBlock
- Add check: if `entry.source._map_block` is not None, it means we're inside a map block and opening another one
- Raise ValueError with clear message: "Nested .map() calls are not supported"

### T22.2 — Update design.md

- Clarify the correct usage: `.map().next()` continues in the same map block, `.map().agg().map()` opens new map blocks

### T22.3 — Fix nyc_taxi example

- Change `.map().map()` to `.map().next()` to chain steps within the same map block

### T22.4 — Unit tests

- Test that nested `.map()` raises ValueError
- Test that `.map().next().agg()` works correctly
- Test error handling for invalid kwargs

---

## Milestone 23 — Step Retry Configuration

_Purpose_: Allow steps to specify retry policies for handling transient failures. Retry is implemented in both local runner and AWS Step Functions deployment.

### T23.1 — Add RetryConfig dataclass

- Add `RetryConfig` dataclass in `decorators.py`:
  - `retries: int = 0` - maximum retry attempts
  - `delay: float = 1.0` - initial delay in seconds
  - `backoff: float = 1.0` - exponential backoff multiplier
  - `max_delay: float = 60.0` - maximum delay cap
  - `exceptions: tuple[type, ...] = (Exception,)` - exception types to catch

### T23.2 — Update StepNode to accept retry config

- Modify `StepNode.__init__` to accept optional `retry` parameter
- Store retry config on the step node

### T23.3 — Update step decorator to accept retry parameter

- Modify `step()` function to accept `retry` keyword argument
- Pass retry config to StepNode constructor

### T23.4 — Update FlowGraph to include retry config

- Ensure retry config is preserved through graph resolution
- Expose retry config in TaskEntry for builders to use

### T23.5 — Implement retry in LocalRunner

- Add `_run_task_with_retry()` method in `runner.py`
- Implement exponential backoff logic
- Handle configurable exception types
- Log retry attempts at INFO level

### T23.6 — Update Lambda handler to accept retry config

- Modify `make_handler()` to accept retry config parameter
- Pass retry config when generating handler (for potential future use)

### T23.7 — Update state machine generation for retry

- Modify `state_machine.py` to generate `Retry` field in Task states
- Map retry config to Step Functions retry field:
  - `retries` → `MaxAttempts` (retries + 1)
  - `delay` → `IntervalSeconds`
  - `backoff` → `BackoffRate`
- Map exception types to AWS error names

### T23.8 — Unit tests for retry config

- Create `tests/test_retry.py`
- Test RetryConfig dataclass defaults and custom values
- Test decorator accepts retry parameter
- Test retry logic in LocalRunner
- Test state machine retry field generation

### T23.9 — Integration test for retry

- Create a flow with a failing step that succeeds on retry
- Verify local execution retries correctly
- Verify build generates correct retry field

---

## Milestone 24 — Code Refactoring

_Purpose_: Enhance code readability and reduce LOC through extraction, consolidation, and elimination of duplication.

### T24.1 — Create _utils.py with shared utilities

- Create `lokki/_utils.py` with:
  - `to_pascal(name: str) -> str` - convert snake_case to PascalCase
  - `to_kebab(name: str) -> str` - convert snake_case to kebab-case
- Update imports in `builder/cloudformation.py`, `builder/state_machine.py`, `builder/sam_template.py`

### T24.2 — Create _errors.py with centralized errors

- Create `lokki/_errors.py` with:
  - `DeployError`
  - `DockerNotAvailableError`
  - `ShowError`
  - `LogsError`
  - `DestroyError`
- Update imports in `deploy.py`, `show.py`, `logs.py`, `destroy.py`

### T24.3 — Create _aws.py with AWS client factory

- Create `lokki/_aws.py` with helper functions:
  - `get_s3_client(endpoint: str = "") -> boto3.client`
  - `get_sfn_client(endpoint: str = "", region: str = "us-east-1") -> boto3.client`
  - `get_cf_client(endpoint: str = "", region: str = "us-east-1") -> boto3.client`
  - `get_logs_client(endpoint: str = "", region: str = "us-east-1") -> boto3.client`
  - `get_ecr_client(endpoint: str = "", region: str = "us-east-1") -> boto3.client`
- Update imports in `deploy.py`, `show.py`, `logs.py`, `destroy.py`

### T24.4 — Create _store.py with LocalStore

- Extract `LocalStore` class from `runner.py` to `lokki/_store.py`
- Move `_to_json_safe()` helper to the new module
- Update imports in `runner.py`

### T24.5 — Extract CLI to cli.py

- Create `lokki/cli.py` with:
  - `_get_flow_params()` - moved from __init__.py
  - `_coerce_value()` - moved from __init__.py
  - `_parse_flow_params()` - moved from __init__.py
  - `_get_step_names()` - moved from __init__.py
  - `_handle_run()` - NEW - extracted command handler
  - `_handle_build()` - NEW - extracted command handler
  - `_handle_deploy()` - NEW - extracted command handler
  - `_handle_show()` - NEW - extracted command handler
  - `_handle_logs()` - NEW - extracted command handler
  - `_handle_destroy()` - NEW - extracted command handler
  - `main()` - refactored to use handlers
- Update `lokki/__init__.py` to import from cli.py

### T24.6 — Create builder/_graph.py

- Create `lokki/builder/_graph.py` with:
  - `get_step_names(graph: FlowGraph) -> set[str]` - consolidated from cloudformation, state_machine, sam_template
- Update imports in builder modules

### T24.7 — Update builder modules

- Update `builder/cloudformation.py`:
  - Use `_utils.to_pascal()` instead of local function
  - Use `builder._graph.get_step_names()` instead of local function
  - Remove `_to_pascal()`, `_get_step_names()`, `_get_module_name()`
- Update `builder/state_machine.py`:
  - Use `_utils.to_pascal()` instead of local function
  - Remove `_to_pascal()`
- Update `builder/sam_template.py`:
  - Use `_utils.to_pascal()` instead of local function
  - Use `builder._graph.get_step_names()` instead of local function
  - Remove `_to_pascal()`, `_get_step_names()`, `_get_module_name()`

### T24.8 — Update runtime handler

- Update `runtime/handler.py` to use `s3` module's existing functions if applicable

### T24.9 — Update pyproject.toml

- Verify package discovery works with new module structure
- Ensure all modules are properly included in the package

### T24.10 — Run all tests

- Run `uv run pytest` to verify no regressions
- Fix any test failures related to import changes

---

## Milestone 25 — Documentation Update

_Purpose_: Update documentation to reflect current implementation and add missing features.

### T25.1 — Update README.md

- Fix configuration section: change `lokki.yml` → `lokki.toml`
- Update YAML syntax → TOML syntax in examples
- Add missing configuration fields from requirements.md
- Add missing CLI commands: `deploy`, `show`, `logs`, `destroy`
- Add `.next()` chaining syntax documentation
- Add flow-level kwargs documentation
- Add retry configuration documentation
- Add ZIP deployment option documentation
- Add LocalStack testing documentation reference

### T25.2 — Fix dev/README.md

- Change all `lokki.yml` references to `lokki.toml`
- Update YAML config examples to TOML
- Fix any outdated command examples

### T25.3 — Fix dev/deploy-localstack.sh

- Change config file reference from `lokki.yml` to `lokki.toml`

### T25.4 — Verify documentation consistency

- Check that all config field names match actual implementation
- Verify all CLI commands documented are implemented
- Ensure examples are accurate

---

## Milestone 26 — Type Safety Improvements

_Purpose_: Fix mypy errors and add type stubs for better type safety.

### T26.1 — Add type stubs dependencies

- Add `boto3-stubs` to dev dependencies in pyproject.toml
- Add `types-PyYAML` to dev dependencies

### T26.2 — Fix graph.py type error

- Fix `MapBlock | None` assignment issue at line 123
- Add proper null handling

### T26.3 — Fix state_machine.py duplicate definition

- Remove duplicate `to_pascal` definition/import

### T26.4 — Fix return type annotations

- Add proper return types to functions returning `Any`
- Add type annotations to untyped function arguments

### T26.5 — Run mypy to verify

- Run `uv run mypy lokki/` to ensure all errors are fixed
- Fix any remaining errors

---

## Milestone 27 — Test Coverage Improvements

_Purpose_: Increase test coverage for under-tested modules.

### T27.1 — Add tests for _utils.py

- Add tests for `to_pascal()`, `to_kebab()`, `get_step_names()`
- Target: 90%+ coverage

### T27.2 — Add tests for logs.py

- Add tests for `_tail_logs()` function
- Add tests for error handling paths
- Target: 80%+ coverage

### T27.3 — Add tests for cli.py

- Add tests for `_handle_show()`, `_handle_logs()`, `_handle_destroy()`
- Add tests for error handling paths
- Target: 80%+ coverage

### T27.4 — Add tests for deploy.py

- Add tests for `_validate_credentials()` Docker checks
- Add tests for `_push_images()` path handling
- Target: 80%+ coverage

### T27.5 — Run coverage report

- Run `uv run pytest --cov=lokki` to verify coverage improvements
- Target overall: 85%+ coverage

---

## Milestone 28 — Security Improvements

_Purpose_: Add security scanning and improve input validation.

### T28.1 — Add pip-audit to dev dependencies

- Add `pip-audit` to dev dependencies in pyproject.toml

### T28.2 — Add pre-commit hook for security

- Add `.pre-commit-config.yaml` with:
  - `detect-secrets` or `gitleaks` for secrets scanning
  - `ruff` for linting
  - `mypy` for type checking

### T28.3 — Add input validation improvements

- Add bounds checking for numeric parameters
- Add S3 URL validation improvements

### T28.4 — Document security policy

- Create `SECURITY.md` with vulnerability reporting instructions

---

## Milestone 29 — CI/CD Setup

_Purpose_: Add continuous integration workflow.

### T29.1 — Create GitHub Actions workflow

- Create `.github/workflows/ci.yml` with:
  - Python 3.13 build
  - pytest test runner
  - mypy type checking
  - ruff linting
  - Coverage reporting

### T29.2 — Add coverage reporting

- Add `coverage-badge` to generate coverage badge
- Configure codecov integration (optional)

### T29.3 — Add pip-audit to CI

- Add pip-audit check to catch vulnerable dependencies

---

## Milestone 30 — Integration Tests

_Purpose_: Add end-to-end integration tests with LocalStack.

### T30.1 — Create integration test fixtures

- Add pytest fixtures for LocalStack S3
- Add pytest fixtures for LocalStack Lambda

### T30.2 — Add full flow integration tests

- Test complete flow: build → deploy → execute → verify
- Test ZIP deployment path
- Test error handling during deployment

### T30.3 — Add Lambda handler tests

- Test Lambda handler with mock events
- Test error handling in Lambda runtime

### T30.4 — Document integration testing

- Add integration test instructions to dev/README.md

---

## Milestone 31 — Migrate to moto for AWS mocking

_Purpose_: Replace MagicMock/patch patterns with moto for more realistic and maintainable AWS testing.

### T31.1 — Migrate test_s3.py to moto

- Replace `@patch("lokki.s3.boto3")` with `@mock_aws`
- Use real S3 operations via boto3 client
- Test actual S3 bucket operations

### T31.2 — Migrate test_show.py to moto

- Replace `@patch("lokki.show.boto3.client")` with `@mock_aws`
- Use real Step Functions client
- Test actual state machine operations

### T31.3 — Migrate test_logs.py to moto

- Replace `@patch("lokki.logs.boto3.client")` with `@mock_aws`
- Use real CloudWatch Logs client
- Test actual log group and stream operations

### T31.4 — Migrate test_destroy.py to moto

- Replace `@patch("lokki.destroy.boto3.client")` with `@mock_aws`
- Use real CloudFormation client
- Test actual stack operations

### T31.5 — Run tests to verify migration

- Run all tests to ensure no regressions
- Verify coverage remains consistent

---

## Milestone 32 — AWS Batch Support

_Purpose_: Add support for running steps as AWS Batch jobs in addition to Lambda functions. This enables compute-intensive workloads that exceed Lambda's constraints.

### T32.1 — Add BatchConfig dataclass

- Add `BatchConfig` dataclass in `config.py`:
  - `job_queue: str = ""` - AWS Batch job queue name
  - `job_definition_name: str = ""` - Base name for generated job definition
  - `timeout_seconds: int = 3600` - Default job timeout
  - `vcpu: int = 2` - Default vCPUs
  - `memory_mb: int = 4096` - Default memory in MB
  - `image: str = ""` - Docker image (defaults to Lambda image)
- Add `batch_cfg: BatchConfig` to `LokkiConfig`

### T32.2 — Add environment variable overrides

- Add `LOKKI_BATCH_JOB_QUEUE` override
- Add `LOKKI_BATCH_JOB_DEFINITION` override

### T32.3 — Add JobTypeConfig dataclass

- Add `JobTypeConfig` dataclass in `decorators.py`:
  - `job_type: str = "lambda"` - "lambda" or "batch"
  - `vcpu: int | None = None` - None = use global config
  - `memory_mb: int | None = None`
  - `timeout_seconds: int | None = None`

### T32.4 — Update StepNode for job_type

- Modify `StepNode.__init__` to accept job_type and step-level parameters
- Add `job_type`, `vcpu`, `memory_mb`, `timeout_seconds` attributes

### T32.5 — Update @step decorator

- Modify `step()` function to accept `job_type`, `vcpu`, `memory_mb`, `timeout_seconds` parameters
- Pass these to StepNode constructor

### T32.6 — Update FlowGraph TaskEntry

- Add job_type, vcpu, memory_mb, timeout_seconds fields to `TaskEntry` dataclass
- Update resolution logic to populate these fields from step or global config

### T32.7 — Add Batch client helper

- Add `get_batch_client(endpoint: str = "", region: str = "us-east-1")` to `lokki/_aws.py`

### T32.8 — Create Batch runtime handler

- Create `lokki/runtime/batch.py` with `make_batch_handler(fn)` function
- Read input from S3, execute step function, write output to S3
- Handle error cases

### T32.9 — Create Batch entry point

- Create `lokki/runtime/batch_main.py` as entry point for Batch jobs
- Reads environment variables, invokes step function

### T32.10 — Update Lambda packaging for Batch

- Update `lambda_pkg.py` to include Batch handler and entry point in packages
- Ensure both Lambda and Batch steps can execute

### T32.11 — Update state machine generation

- Modify `state_machine.py` to check step's `job_type`
- Generate Lambda Invoke task for `job_type="lambda"`
- Generate Batch SubmitJob task for `job_type="batch"`
- Pass step-specific vcpu, memory via task parameters

### T32.12 — Update CloudFormation template

- Add `BatchJobQueue` and `BatchJobDefinitionName` parameters
- Add `AWS::Batch::JobDefinition` resource
- Add `BatchExecutionRole` IAM role
- Update StepFunctions IAM role with Batch permissions

### T32.13 — Update SAM template for Batch

- Add Batch Job Definition to SAM template if needed
- Handle mixed Lambda/Batch deployment

### T32.14 — Update LocalRunner for Batch

- Modify `runner.py` to detect Batch steps
- Implement realistic mocking with moto for Batch API:
  - Mock Batch client
  - Simulate job submission, status polling
  - Execute function inline and return result

### T32.15 — Unit tests for Batch config

- Add tests for BatchConfig parsing in `test_config.py`
- Test environment variable overrides

### T32.16 — Unit tests for job_type decorator

- Add tests in `test_decorators.py` for job_type parameter
- Test step-level vcpu/memory overrides

### T32.17 — Unit tests for Batch state machine

- Add tests in `test_state_machine.py` for mixed Lambda/Batch flows
- Test Batch task has correct SubmitJob.sync resource

### T32.18 — Unit tests for Batch handler

- Create `tests/test_batch.py`
- Test batch handler reads input, executes function, writes output

### T32.19 — Integration test for Batch

- Add integration test in `test_integration.py` for Batch step execution
- Test local run with moto mocking

### T32.20 — Update documentation

- Ensure `docs/requirements.md` reflects Batch support
- Ensure `docs/design.md` reflects Batch architecture
- Add example to README showing Batch usage

---

## Milestone 33 — Map Concurrency Limit

_Purpose_: Add Step Functions Map state concurrency limit to control parallel execution.

### T33.1 — Add concurrency_limit to MapBlock

- Add `concurrency_limit: int | None = None` parameter to `MapBlock.__init__()`
- Store concurrency_limit on the MapBlock instance

### T33.2 — Update StepNode.map() to accept concurrency_limit

- Modify `StepNode.map()` to accept `concurrency_limit` parameter
- Pass it to the newly created `MapBlock`

### T33.3 — Update graph.py MapOpenEntry

- Add `concurrency_limit: int | None` field to `MapOpenEntry` dataclass
- Update FlowGraph resolution to populate this field from MapBlock

### T33.4 — Update state machine generation

- Modify `state_machine.py` to add `MaxConcurrency` to Map state when set
- Map the concurrency_limit value to the AWS Step Functions MaxConcurrency field

### T33.5 — Update SAM template generation

- Add MaxConcurrency to Map state in SAM template if applicable

### T33.6 — Unit tests

- Add tests for concurrency_limit in decorators and graph
- Add tests for state machine MaxConcurrency generation

### T33.7 — Update documentation

- Add concurrency_limit usage to docs/design.md
- Add example to README

---

## Milestone 34 — API Documentation

_Purpose_: Create comprehensive API documentation and add docstrings to source code.

### T34.1 — Create docs/api.md

- Create comprehensive API reference document covering:
  - `@step` decorator with all parameters (retry, job_type, vcpu, memory_mb, timeout_seconds)
  - `@flow` decorator
  - StepNode chaining methods (`.map()`, `.next()`, `.agg()`)
  - MapBlock methods
  - RetryConfig dataclass
  - CLI commands (run, build, deploy, show, logs, destroy)
  - Configuration schema (all TOML fields)
  - Environment variables
  - Complete usage examples

### T34.2 — Add docstrings to decorators.py

- Add module-level docstring
- Add class docstrings to StepNode, MapBlock
- Add comprehensive docstrings to step(), flow() functions
- Document all parameters and examples

### T34.3 — Add docstrings to config.py

- Add module-level docstring with configuration overview
- Add docstrings to LambdaConfig, BatchConfig, LokkiConfig dataclasses
- Document all configuration fields
- Add configuration precedence explanation

### T34.4 — Add docstrings to runner.py

- Add module-level docstring
- Add docstrings to LocalRunner class and run() method

### T34.5 — Add docstrings to s3.py

- Add module-level docstring with serialization explanation
- Document write(), read(), write_manifest(), set_endpoint() functions

### T34.6 — Add docstrings to builder modules

- Add module-level docstrings to builder.py, state_machine.py, cloudformation.py, lambda_pkg.py, sam_template.py
- Add docstrings to Builder class and build functions

### T34.7 — Add docstrings to deploy.py

- Add module-level docstring
- Add docstrings to Deployer class and deploy methods

### T34.8 — Add remaining docstrings

- Add docstrings to graph.py (FlowGraph, TaskEntry, MapOpenEntry, MapCloseEntry)
- Add docstrings to logging.py
- Add docstrings to cli.py
