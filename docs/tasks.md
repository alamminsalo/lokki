# lokki — Implementation Tasks

Tasks are grouped by milestone. Each milestone should be completable and testable independently. Dependencies between tasks are noted where relevant.

- [x] = Completed
- [ ] = Not yet completed

---

## Milestone 1 — Project Scaffolding

- [x] **T1.1** Initialise the project with `uv init`, configure `pyproject.toml` with package metadata and dependencies (`boto3`).

- [x] **T1.2** Create the full directory skeleton as defined in the design:
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

- [x] **T1.3** Write `lokki/__init__.py` exporting the public API: `flow`, `step`, `main`.

---

## Milestone 2 — Configuration (`lokki/config.py`)

- [x] **T2.1** Implement `_load_toml(path)` — loads a TOML file, returns empty dict if file does not exist. Uses Python's stdlib `tomllib` (requires Python 3.11+).

- [x] **T2.2** Implement `_deep_merge(base, override)` — recursively merges two dicts; scalars and lists in `override` replace those in `base`; nested dicts are merged recursively.

- [x] **T2.3** Implement `LokkiConfig`, `AwsConfig`, `RolesConfig`, `LambdaConfig`, and `LoggingConfig` dataclasses with all fields and defaults as per the new config schema:
- `aws.artifact_bucket`, `aws.ecr_repo_prefix`, `aws.roles`
- `lambda.timeout`, `lambda.memory`, `lambda.image_tag`, `lambda.env`
- `build_dir`, `logging`

- [x] **T2.4** Implement `load_config()` — loads global (`~/.lokki/lokki.toml`) then local (`./lokki.toml`), deep-merges them, applies environment variable overrides (`LOKKI_ARTIFACT_BUCKET`, `LOKKI_ECR_REPO_PREFIX`, `LOKKI_BUILD_DIR`), returns a populated `LokkiConfig`.

- [x] **T2.5** Write unit tests for `_deep_merge` covering: scalar override, list replacement, nested dict merge, missing keys in either file, neither file present.

- [x] **T2.6** Update config schema for new format

- [x] **T2.7** Update config loading for new format

---

## Milestone 3 — Decorator & Graph Model

_Depends on: M1_

- [x] **T3.1** Implement `StepNode` class in `decorators.py`:
- `__init__(fn)` — stores function, name, default args, next pointer
- `__call__(*args, **kwargs)` — records default args, returns `self`
- `map(step_node)` — creates and returns a `MapBlock`
- `agg(step_node)` — raises `TypeError` (must be called on `MapBlock`)

- [x] **T3.2** Implement `MapBlock` class in `decorators.py`:
- `__init__(source, inner_head)` — stores source step and inner chain head/tail
- `map(step_node)` — appends step to the inner chain, returns `self`
- `agg(step_node)` — closes the block, attaches aggregation step, returns the `StepNode`

- [x] **T3.3** Implement `step` decorator function — wraps `fn` in a `StepNode` and returns it.

- [x] **T3.4** Implement `FlowGraph` in `graph.py`:
- `__init__(name, head)` — stores name, calls `_resolve(head)`
- `_resolve(head)` — walks the chain and populates `self.entries` as an ordered list of `TaskEntry | MapOpenEntry | MapCloseEntry`

- [x] **T3.5** Implement `flow` decorator function — wraps `fn` so calling it invokes the body, collects the returned chain, and returns a `FlowGraph` with `name` derived from `fn.__name__`.

- [x] **T3.6** Write unit tests for the decorator and graph covering: single task, linear chain, `.map().agg()`, chaining after `.agg()`, calling `.agg()` directly on a `StepNode` raises `TypeError`, flow name derivation from function name.

- [x] **T3.7** Implement `.next()` method on StepNode

- [x] **T3.8** Implement `.next()` method on MapBlock

- [x] **T3.9** Update FlowGraph resolution for sequential chaining

- [x] **T3.10** Add error handling for invalid flows

- [x] **T3.11** Update unit tests for `.next()`

- [x] **T3.12** Update LocalRunner for multiple inner Map steps

- [x] **T3.13** Update state machine generation for `.next()` in Map

---

## Milestone 4 — CLI Entry Point

_Depends on: M3_

- [x] **T4.1** Implement `main(flow_fn)` in `lokki/__init__.py` (or a dedicated `cli.py`):
- Parses `sys.argv[1]`
- `build` → resolves `FlowGraph`, calls `Builder.build(graph, config)`
- `run` → resolves `FlowGraph`, calls `LocalRunner.run(graph)`
- Anything else → prints usage and exits with code 1

- [x] **T4.2** The `@flow` decorator is combined with an explicit `main(flow_fn)` call in the `if __name__ == "__main__"` block. Users add `main(my_flow)` at the bottom of their script.

---

## Milestone 5 — S3 & Serialisation Layer (`lokki/s3.py`)

_Depends on: M1_

- [x] **T5.1** Implement `write(bucket, key, obj) -> str` — serialises `obj` with `pickle.dumps` at `HIGHEST_PROTOCOL`, compresses with `gzip.compress`, uploads via `boto3`, returns the `s3://bucket/key` URL.

- [x] **T5.2** Implement `read(url) -> Any` — parses the S3 URL, downloads the object via `boto3`, decompresses and unpickles, returns the Python object.

- [x] **T5.3** Implement `_parse_url(url) -> (bucket, key)` — splits an `s3://` URL into bucket and key components.

- [x] **T5.4** Write unit tests using `moto` (or `unittest.mock`) to mock S3: round-trip write then read, URL parsing, error on malformed URL.

---

## Milestone 6 — Local Runner (`lokki/runner.py`)

_Depends on: M3, M5_

- [x] **T6.1** Implement `LocalStore` — mirrors the `s3.py` interface (`read`, `write`) but stores gzip-pickled files under a local temp directory keyed by step name and index.

- [x] **T6.2** Implement `LocalRunner.run(graph)`:
- Creates a `LocalStore` in a temp directory
- Iterates `graph.entries`
- `TaskEntry` → calls step function with resolved inputs from store, writes output to store
- `MapOpenEntry` → fans out using `ThreadPoolExecutor`, running the inner step chain for each item in the source step's output list; writes per-item results to store
- `MapCloseEntry` → collects all per-item results, passes as list to aggregation function, writes output to store

- [x] **T6.3** Write integration tests running the full birds example locally, asserting the final output equals `"flappy goose, flappy duck, flappy seagul"`.

---

## Milestone 7 — Runtime Handler (`lokki/runtime/handler.py`)

_Depends on: M5_

- [x] **T7.1** Implement `make_handler(fn) -> lambda_handler`:
- Reads `LOKKI_ARTIFACT_BUCKET` and `LOKKI_FLOW_NAME` from environment via `load_config()`
- Reads `run_id` from the event
- Resolves inputs: no upstream (first step) → passes event kwargs matching function signature; `result_url` present → downloads single object; `result_urls` present → downloads list and passes as single list arg
- Calls `fn` with resolved inputs
- Writes result to S3 at `lokki/<flow_name>/<run_id>/<step_name>/output.pkl.gz`
- If result is a list and step is a map source, also writes a map manifest JSON to `lokki/<flow_name>/<run_id>/<step_name>/map_manifest.json`
- Returns `{"result_url": "...", "run_id": "..."}` or `{"map_manifest_key": "...", "run_id": "..."}` for map sources

- [x] **T7.2** Write unit tests for `make_handler` covering: first step with no input, first step with event overrides, single input via `result_url`, list input via `result_urls`, map source writing manifest.

---

## Milestone 8 — Lambda Packaging (`lokki/builder/lambda_pkg.py`)

_Depends on: M3, M2_

- [x] **T8.1** Implement `generate_shared_lambda_files(graph, config, build_dir)`:
- Creates `<build_dir>/lambdas/` directory (shared, not per-step)
- Writes the shared `Dockerfile` (multi-stage, using AWS Lambda Python base image, installing deps from user's `pyproject.toml` via `uv`, copying the generated `handler.py`)
- Writes the auto-generated `handler.py` that dynamically imports the step function based on `LOKKI_STEP_NAME` and `LOKKI_MODULE_NAME` environment variables

- [x] **T8.2** Implement shared Dockerfile template:
- Single template for all steps (not per-step)
- Parameterised on the Python base image tag from `lambda.image_tag`
- Installs dependencies from user's `pyproject.toml` (which must include `lokki`)

- [x] **T8.3** Write tests asserting the generated `Dockerfile` contains the expected `FROM`, `COPY`, `RUN uv pip install`, and `CMD` lines; and that `handler.py` reads `LOKKI_STEP_NAME` and `LOKKI_MODULE_NAME` env vars.

---

## Milestone 9 — State Machine Generation (`lokki/builder/state_machine.py`)

_Depends on: M3, M2_

- [x] **T9.1** Implement `build_state_machine(graph, config) -> dict` — returns a valid Amazon States Language dict.

- [x] **T9.2** Implement `_task_state(step_node, config) -> dict` — generates a `Task` state invoking the step's Lambda ARN (constructed from `ecr_repo_prefix`, flow name, and step name), with `ResultPath` passing only the S3 result URL.

- [x] **T9.3** Implement `_map_state(map_open_entry, config) -> dict` — generates a `Map` state in `DISTRIBUTED` mode with:
- `ItemReader` pointing to the map manifest JSON in S3
- `ItemProcessor` containing the inner step chain as a nested state machine
- `ResultWriter` writing collected results back to S3

- [x] **T9.4** Implement the linear chaining of states using `Next` and `End` fields, ensuring correct ordering from `graph.entries`.

- [x] **T9.5** Write unit tests asserting the birds example produces a state machine with: a `GetBirds` Task state, a `Map` state containing `FlapBird`, and a `JoinBirds` Task state; correct `Next` pointers; and `"End": true` on the final state.

---

## Milestone 10 — CloudFormation Generation (`lokki/builder/cloudformation.py`)

_Depends on: M9, M2_

- [x] **T10.1** Implement `build_template(graph, config) -> str` — returns a valid CloudFormation YAML string.

- [x] **T10.2** Implement Lambda function resource generation (one per step) with: `PackageType: Image`, `ImageUri` referencing ECR, `Role` from `config.aws.roles.lambda_`, `Timeout` and `MemorySize` from `lambda`, environment variables from `lambda.env` plus `LOKKI_ARTIFACT_BUCKET` and `LOKKI_FLOW_NAME`.

- [x] **T10.3** Implement IAM role resources: `LambdaExecutionRole` (S3 read/write on lokki prefix, CloudWatch Logs) and `StepFunctionsExecutionRole` (Lambda invoke, S3 read/write for Distributed Map result writing). Use ARNs from `config.aws.roles` if provided, otherwise generate the role resources.

- [x] **T10.4** Implement the Step Functions state machine resource with the state machine JSON inlined via `DefinitionString` and `!Sub` for Lambda ARN interpolation.

- [x] **T10.5** Implement the Parameters block (`FlowName`, `S3Bucket`, `ECRRepoPrefix`, `ImageTag`).

- [x] **T10.6** Write tests asserting the generated YAML is valid (`yaml.safe_load` parses without error) and contains expected resource logical IDs for each step.

---

## Milestone 11 — Build Orchestrator (`lokki/builder/builder.py`)

_Depends on: M8, M9, M10_

- [x] **T11.1** Implement `Builder.build(graph, config)`:
- Creates `<config.build_dir>/` output directory
- Calls `generate_lambda_dir` for each step node in `graph.nodes`
- Calls `build_state_machine` and writes output to `<build_dir>/statemachine.json`
- Calls `build_template` and writes output to `<build_dir>/template.yaml`
- Prints a summary of generated files

- [x] **T11.2** Write an integration test running `build` on the birds example and asserting all expected files exist in the output directory with non-empty content.

---

## Milestone 12 — End-to-End & Hardening

- [x] **T12.1** Write a full end-to-end local run test from CLI invocation (`python birds_flow_example.py run`) asserting the final printed or returned output.

- [x] **T12.2** Write a full build test from CLI invocation (`python birds_flow_example.py build`) asserting all artifacts are generated.

- [x] **T12.3** Add clear error messages for common user mistakes: missing `artifact_bucket` in config, `@flow` function not returning a chain, `.agg()` called without a preceding `.map()`.

- [x] **T12.4** Add a `--help` flag to the CLI that prints available commands and a short description.

- [x] **T12.5** Write a `README.md` covering: installation, quickstart with the birds example, `lokki.toml` configuration reference, `build` and `run` commands, and deploying the CloudFormation stack.

---

## Milestone 13 — Logging & Observability

_Depends on: M2, M6_

- [x] **T13.1** Implement `LoggingConfig` dataclass in `config.py`:
- `level`: str = "INFO" (DEBUG, INFO, WARNING, ERROR)
- `format`: str = "human" (human or json)
- `progress_interval`: int = 10
- `show_timestamps`: bool = True

Add environment variable override: `LOKKI_LOG_LEVEL`.

- [x] **T13.2** Implement `lokki/logging.py`:
- `get_logger(name, config)` factory function
- `StepLogger` class with `start()`, `complete(duration)`, `fail(duration, error)` methods
- `MapProgressLogger` class with `start(total_items)`, `update(status)`, `complete()` methods
- `HumanFormatter` and `JsonFormatter` classes

- [x] **T13.3** Implement human-readable formatter:
- Step start: `[INFO] Step 'step_name' started at 2024-01-15T10:30:00`
- Step complete: `[INFO] Step 'step_name' completed in 2.345s (status=success)`
- Step fail: `[ERROR] Step 'step_name' failed after 1.234s: ValueError: invalid input`
- Progress bar: `[=====>                    ] 30/100 (30%) completed`

- [x] **T13.4** Implement JSON formatter:
- Each log line is a JSON object with: level, ts, event, step, duration, status, message
- Example: `{"level": "INFO", "ts": "2024-01-15T10:30:00.123Z", "event": "step_start", "step": "get_data"}`

- [x] **T13.5** Integrate logging into `LocalRunner`:
- Wrap `_run_task()` with step start/complete/fail logging
- Wrap `_run_map()` with map progress tracking
- Wrap `_run_agg()` with step logging

- [x] **T13.6** Write unit tests for logging module:
- Test `StepLogger` output formats
- Test `MapProgressLogger` progress updates
- Test JSON formatter output
- Test configuration loading from lokki.toml

- [x] **T13.7** Integrate logging into Lambda runtime handler:
- Log function invocation
- Log input processing
- Log execution duration
- Log errors with stack traces

---

## Milestone 14 — Deploy Command

_Depends on: M11, M12_

- [x] **T14.1** Implement `lokki/deploy.py`:
- `Deployer` class with `__init__(stack_name, region, image_tag)`
- `deploy(graph, config)` method that orchestrates the full deploy
- `_validate_credentials()` - verify AWS credentials are configured
- `_push_images(ecr_prefix)` - build and push Docker images to ECR
- `_deploy_stack(config)` - deploy CloudFormation stack

- [x] **T14.2** Implement Docker image build and push:
- Build a single shared Docker image from `lokki-build/lambdas/Dockerfile`
- Tag image with `<ecr_repo_prefix>/lokki:<image_tag>`
- Push to ECR using `docker push`
- Handle Docker not installed error gracefully

- [x] **T14.2a** Update CloudFormation to use shared image with env vars:
- Each Lambda function references the same Docker image URI
- Use `PackageType: Image` with `ImageUri` pointing to shared image (`lokki:<image_tag>`)
- Pass `LOKKI_STEP_NAME` and `LOKKI_MODULE_NAME` environment variables per function
- Handler dispatches to correct step based on these env vars

- [x] **T14.2b** Support empty `ecr_repo_prefix` for local testing:
- When `aws.ecr_repo_prefix` is empty, skip ECR push entirely
- Use local Docker image names directly (`<step>:<image_tag>`)
- Update CloudFormation to use local image URIs when ECR prefix is empty
- Useful for LocalStack or local development testing

- [x] **T14.2c** Support `aws.endpoint` for local AWS services:
- Add `endpoint` field to `AwsConfig` (e.g., `http://localhost:4566` for LocalStack)
- Pass endpoint to boto3 clients in deploy.py and runtime handler
- When endpoint is set, configure boto3 to use it for S3, Lambda, Step Functions, CloudFormation, ECR
- Skip Docker login/push validation when using local endpoint

- [x] **T14.3** Implement CloudFormation deployment:
- Use boto3 to create or update stack
- Pass parameters: FlowName, S3Bucket, ECRRepoPrefix, ImageTag
- Wait for stack creation/update to complete
- Report stack status and output

- [x] **T14.4** Add `deploy` command to CLI:
- Parse `--stack-name`, `--region`, `--image-tag`, `--confirm` arguments
- Call `Deployer.deploy(graph, config)`
- Print success/failure messages

- [x] **T14.5** Add error handling:
- Docker not available: clear error message with installation instructions
- ECR authorization: prompt to run `aws ecr get-login-password`
- CloudFormation errors: display error and suggest fixes

- [x] **T14.6** Write integration tests:
- Test deploy with mocked AWS clients
- Test image build and push
- Test CloudFormation stack creation

---

## Milestone 15 — Local Testing with LocalStack

_Purpose_: Enable full pipeline testing locally using LocalStack. This provides an AWS simulation environment that catches deployment and integration issues early.

- [x] **T15.1** ZIP Package with Dispatcher Handler
- [x] **T15.2** CloudFormation ZIP Support
- [x] **T15.3** CloudFormation ZIP Support
- [x] **T15.4** S3 Endpoint Configuration
- [x] **T15.5** Runtime Handler Endpoint Support

---

## Milestone 16 — LocalStack Step Functions

_Purpose_: Deploy and test the full Step Functions state machine locally using LocalStack. This enables end-to-end pipeline testing without real AWS.

- [x] **T16.1** LocalStack Step Functions Support
- [x] **T16.2** Integration Test
- [x] **T16.3** Dev Scripts

---

## Milestone 17 — TOML Configuration Format

_Purpose_: Replace YAML configuration with TOML using Python stdlib. This removes the `pyyaml` dependency and leverages Python 3.11+'s built-in `tomllib` module.

- [x] **T17.1** Update config file naming (TOML implemented in M2)
- [x] **T17.2** Update config loading (TOML implemented in M2)
- [x] **T17.3** Update configuration schema documentation
- [x] **T17.4** Environment variable handling
- [x] **T17.5** Backward compatibility (optional)
- [x] **T17.6** Update tests
- [x] **T17.7** Update builder integration
- [x] **T17.8** Update documentation
- [x] **T17.9** Remove stepfunctions pip dependency (not a pip dep, was removed)

---

## Milestone 18 — Test Coverage Improvements

_Purpose_: Improve test coverage for untested modules. Add `moto` for AWS mocking in tests.

- [x] **T18.1** Add moto to dev dependencies
- [x] **T18.2** Test graph.py
- [x] **T18.3** Test state_machine.py
- [x] **T18.4** Test cloudformation.py
- [ ] **T18.5** (not defined)
- [x] **T18.6** Test builder.py
- [x] **T18.7** Test deploy.py

---

## Milestone 19 — CLI Commands: show, logs, destroy

_Purpose_: Implement AWS integration commands for viewing run status, fetching logs, and destroying stacks.

- [x] **T19.1** Implement show command
- [x] **T19.2** Implement logs command
- [x] **T19.3** Implement destroy command
- [x] **T19.4** Update CLI main function
- [x] **T19.5** Unit tests for show
- [x] **T19.6** Unit tests for logs
- [x] **T19.7** Unit tests for destroy

---

## Milestone 20 — Flow-level Parameters in `.next()`

_Purpose_: Allow passing flow-level parameters directly to steps via `.next(step, param=val)` without threading through intermediate steps.

- [x] **T20.1** Update decorators.py
- [x] **T20.2** Update runner.py
- [x] **T20.3** Unit tests

---

## Milestone 21 — Flow-level Parameters in `.map()` and `.agg()`

_Purpose_: Extend flow-level parameters support to `.map()` and `.agg()` methods.

- [x] **T21.1** Update MapBlock decorators
- [x] **T21.2** Update runner.py for map blocks
- [x] **T21.3** Unit tests

---

## Milestone 22 — Validate Nested .map() Blocks

_Purpose_: Detect and report nested `.map()` blocks which are not supported.

- [x] **T22.1** Update graph.py validation
- [x] **T22.2** Update design.md
- [x] **T22.3** Fix nyc_taxi example
- [x] **T22.4** Unit tests

---

## Milestone 23 — Step Retry Configuration

_Purpose_: Allow steps to specify retry policies for handling transient failures. Retry is implemented in both local runner and AWS Step Functions deployment.

- [x] **T23.1** Add RetryConfig dataclass
- [x] **T23.2** Update StepNode to accept retry config
- [x] **T23.3** Update step decorator to accept retry parameter
- [x] **T23.4** Update FlowGraph to include retry config
- [x] **T23.5** Implement retry in LocalRunner
- [x] **T23.6** Update Lambda handler to accept retry config
- [x] **T23.7** Update state machine generation for retry
- [x] **T23.8** Unit tests for retry config
- [x] **T23.9** Integration test for retry

---

## Milestone 24 — Code Refactoring

_Purpose_: Enhance code readability and reduce LOC through extraction, consolidation, and elimination of duplication.

- [x] **T24.1** Create _utils.py with shared utilities
- [x] **T24.2** Create _errors.py with centralized errors
- [x] **T24.3** Create _aws.py with AWS client factory
- [x] **T24.4** Create _store.py with LocalStore
- [x] **T24.5** Extract CLI to cli.py
- [x] **T24.6** Create builder/_graph.py
- [x] **T24.7** Update builder modules
- [x] **T24.8** Update runtime handler
- [x] **T24.9** Update pyproject.toml
- [x] **T24.10** Run all tests

---

## Milestone 25 — Documentation Update

_Purpose_: Update documentation to reflect current implementation and add missing features.

- [x] **T25.1** Update README.md
- [x] **T25.2** Fix dev/README.md
- [x] **T25.3** Fix dev/deploy-localstack.sh
- [x] **T25.4** Verify documentation consistency

---

## Milestone 26 — Type Safety Improvements

_Purpose_: Fix mypy errors and add type stubs for better type safety.

- [x] **T26.1** Add type stubs dependencies
- [x] **T26.2** Fix graph.py type error
- [x] **T26.3** Fix state_machine.py duplicate definition
- [x] **T26.4** Fix return type annotations
- [x] **T26.5** Run mypy to verify

---

## Milestone 27 — Test Coverage Improvements

_Purpose_: Increase test coverage for under-tested modules.

- [x] **T27.1** Add tests for _utils.py
- [x] **T27.2** Add tests for logs.py
- [x] **T27.3** Add tests for cli.py
- [x] **T27.4** Add tests for deploy.py
- [x] **T27.5** Run coverage report

---

## Milestone 28 — Security Improvements

_Purpose_: Add security scanning and improve input validation.

- [x] **T28.1** Add pip-audit to dev dependencies
- [x] **T28.2** Add pre-commit hook for security
- [x] **T28.3** Add input validation improvements
- [x] **T28.4** Document security policy

---

## Milestone 29 — CI/CD Setup

_Purpose_: Add continuous integration workflow.

- [x] **T29.1** Create GitHub Actions workflow
- [x] **T29.2** Add coverage reporting
- [x] **T29.3** Add pip-audit to CI

---

## Milestone 30 — Integration Tests

_Purpose_: Add end-to-end integration tests with LocalStack.

- [x] **T30.1** Create integration test fixtures
- [x] **T30.2** Add full flow integration tests
- [x] **T30.3** Add Lambda handler tests
- [x] **T30.4** Document integration testing

---

## Milestone 31 — Migrate to moto for AWS mocking

_Purpose_: Replace MagicMock/patch patterns with moto for more realistic and maintainable AWS testing.

- [x] **T31.1** Migrate test_s3.py to moto
- [x] **T31.2** Migrate test_show.py to moto
- [x] **T31.3** Migrate test_logs.py to moto
- [x] **T31.4** Migrate test_destroy.py to moto
- [x] **T31.5** Run tests to verify migration

---

## Milestone 32 — AWS Batch Support

_Purpose_: Add support for running steps as AWS Batch jobs in addition to Lambda functions. This enables compute-intensive workloads that exceed Lambda's constraints.

- [x] **T32.1** Add BatchConfig dataclass
- [x] **T32.2** Add environment variable overrides
- [x] **T32.3** Add JobTypeConfig dataclass
- [x] **T32.4** Update StepNode for job_type
- [x] **T32.5** Update @step decorator
- [x] **T32.6** Update FlowGraph TaskEntry
- [x] **T32.7** Add Batch client helper
- [x] **T32.8** Create Batch runtime handler
- [x] **T32.9** Create Batch entry point
- [x] **T32.10** Update Lambda packaging for Batch
- [x] **T32.11** Update state machine generation
- [x] **T32.12** Update CloudFormation template
- [x] **T32.14** Update LocalRunner for Batch
- [x] **T32.15** Unit tests for Batch config
- [x] **T32.16** Unit tests for job_type decorator
- [x] **T32.17** Unit tests for Batch state machine
- [x] **T32.18** Unit tests for Batch handler
- [x] **T32.19** Integration test for Batch
- [x] **T32.20** Update documentation

---

## Milestone 33 — Map Concurrency Limit

_Purpose_: Add Step Functions Map state concurrency limit to control parallel execution.

- [x] **T33.1** Add concurrency_limit to MapBlock
- [x] **T33.2** Update StepNode.map() to accept concurrency_limit
- [x] **T33.3** Update graph.py MapOpenEntry
- [x] **T33.4** Update state machine generation
- [x] **T33.5** Update CloudFormation template generation
- [x] **T33.6** Unit tests
- [x] **T33.7** Update documentation

---

## Milestone 34 — API Documentation

_Purpose_: Create comprehensive API documentation and add docstrings to source code.

- [x] **T34.1** Create docs/api.md
- [x] **T34.2** Add docstrings to decorators.py
- [x] **T34.3** Add docstrings to config.py
- [x] **T34.4** Add docstrings to runner.py
- [x] **T34.5** Add docstrings to s3.py
- [x] **T34.6** Add docstrings to builder modules
- [x] **T34.7** Add docstrings to deploy.py
- [x] **T34.8** Add remaining docstrings

---

## Summary

| Milestone | Status |
|-----------|--------|
| M1 - Project Scaffolding | Complete |
| M2 - Configuration | Complete |
| M3 - Decorator & Graph Model | Complete |
| M4 - CLI Entry Point | Complete |
| M5 - S3 & Serialisation Layer | Complete |
| M6 - Local Runner | Complete |
| M7 - Runtime Handler | Complete |
| M8 - Lambda Packaging | Complete |
| M9 - State Machine Generation | Complete |
| M10 - CloudFormation Generation | Complete |
| M11 - Build Orchestrator | Complete |
| M12 - End-to-End & Hardening | Complete |
| M13 - Logging & Observability | Complete |
| M14 - Deploy Command | Complete |
| M15 - Local Testing with LocalStack | Complete |
| M16 - Step Functions Local Deployment | Complete |
| M17 - TOML Configuration Format | Complete |
| M18 - Test Coverage Improvements | Complete |
| M19 - CLI Commands: show, logs, destroy | Complete |
| M20 - Flow-level Parameters in .next() | Complete |
| M21 - Flow-level Parameters in .map() and .agg() | Complete |
| M22 - Validate Nested .map() Blocks | Complete |
| M23 - Step Retry Configuration | Complete |
| M24 - Code Refactoring | Complete |
| M25 - Documentation Update | Complete |
| M26 - Type Safety Improvements | Complete |
| M27 - Test Coverage Improvements | Complete |
| M28 - Security Improvements | Complete |
| M29 - CI/CD Setup | Complete |
| M30 - Integration Tests | Complete |
| M31 - Migrate to moto for AWS mocking | Complete |
| M32 - AWS Batch Support | Complete |
| M33 - Map Concurrency Limit | Complete |
| M34 - API Documentation | Complete |
| M35 - Scheduling | Complete |
| M36 - Unify Store Interfaces | Complete |

---

## Milestone 36 — Unify Store Interfaces

_Purpose_: Unify LocalStore and S3Store interfaces. Both should have consistent constructors, and S3Store should read bucket from environment variables internally (not passed by callers).

- [x] **T36.1** Update S3Store constructor
  - Remove `bucket` parameter
  - Read `LOKKI_ARTIFACT_BUCKET` from environment internally
  - Accept only `endpoint` parameter

- [x] **T36.2** Update LocalStore interface
  - Remove `bucket` and `key` parameters from `write()` and `write_manifest()`
  - Keep only `flow_name`, `run_id`, `step_name` parameters

- [x] **T36.3** Rename DataStore protocol to TransientStore
  - Update protocol to reflect unified interface
  - Make flow_name, run_id, step_name required (not Optional)

- [x] **T36.4** Update runtime callers
  - `handler.py`: Change `S3Store(bucket, endpoint)` → `S3Store(endpoint)`
  - `batch.py`: Same change

- [x] **T36.5** Update tests
  - Fix S3Store constructor calls (remove bucket arg)
  - Remove bucket/key tests from LocalStore

- [x] **T36.6** Run tests and verify coverage

---

## Milestone 37 — S3 Directory Structure Refactoring

This milestone refactors the S3 directory structure to separate flow runs from permanent artifacts.

### Background

Currently, all S3 data is stored under a single bucket structure. This makes it difficult to distinguish between:
- **Ephemeral data**: Flow run outputs, intermediate results, logs (can be cleaned up after runs complete)
- **Permanent artifacts**: Lambda deployment packages, shared data (should persist across runs)

### New S3 Directory Structure

```
s3://<artifact-bucket>/
└── <flow-name>/
    ├── runs/
    │   └── <run-id>/
    │       └── <step-name>/
    │           ├── output.pkl.gz
    │           └── map_manifest.json
    └── artifacts/
        └── lambdas/
            └── function.zip
```
s3://<artifact-bucket>/
└── <flow-name>/
    ├── runs/
    │   └── <run-id>/
    │       └── <step-name>/
    │           ├── output.pkl.gz
    │           └── map_manifest.json
    └── artifacts/
        └── lambdas/
            └── function.zip
```

### Tasks

- [ ] **T37.1** Update S3Store to use new directory structure
  - Modify `_make_key()` to use `<flow_name>/runs/<run_id>/<step_name>/` prefix
  - Add new method for writing Lambda packages to `<flow_name>/artifacts/` prefix
  - Update `write_manifest()` to use runs path

- [ ] **T37.2** Update state machine to use new Lambda package location
  - Modify CloudFormation template to reference `s3://<bucket>/<flow-name>/artifacts/lambdas/function.zip`
  - Update state machine generation to use new path

- [ ] **T37.3** Update builder to upload Lambda packages to new location
  - Modify upload command in deploy to use `artifacts/` prefix
  - Update S3 upload path in Taskfile.yaml

- [x] **T37.4** Add S3Store method for Lambda package upload
  - `upload_lambda_zip(flow_name, zip_data) -> str` - returns S3 URI

- [ ] **T37.5** Update tests for new directory structure
  - Add tests for new key prefixes
  - Add tests for Lambda package operations
  - Verify backward compatibility or migration path

- [ ] **T37.6** Update documentation
  - Document new S3 directory structure in docs/config.md
  - Update examples to reflect new paths

---

## Milestone 38 — Lambda Event Dataclass Refactoring

_This milestone refactors the Lambda/Batch runtime handlers to use typed dataclasses for event handling, making the code simpler and more maintainable. It leverages AWS Step Functions Context Object to pass flow parameters without explicit flow passing._

### Background

The current handler code has complex branching logic to handle different input patterns (result_url, result_urls, item_url, aggregation lists, etc.). This makes it hard to maintain and error-prone.

AWS Step Functions provides a Context Object (`$$.Execution.Id`, `$$.Execution.Input`, etc.) that can be used to access execution metadata. lokki uses this to get run_id and flow parameters directly in the Lambda handler, eliminating the need for:
1. InitFlow Pass state
2. Flow context in manifest items
3. Complex event parsing logic

### New Event Structure

```python
@dataclass
class FlowContext:
    run_id: str
    params: dict[str, Any] = field(default_factory=dict)

@dataclass  
class LambdaEvent:
    flow: FlowContext
    input: Any = None  # Data or S3 URL string
```

### Tasks

- [x] **T38.1** Create `lokki/runtime/event.py` with dataclass definitions
  - Define `FlowContext` dataclass with `run_id` and `params` fields
  - Define `LambdaEvent` dataclass with `flow` and `input` fields
  - Add serialization/deserialization helpers for JSON conversion

- [x] **T38.2** Update Lambda handler to use LambdaEvent dataclass
  - Simplify handler to read from `event.input`
  - Read flow params from `event.flow.params`
  - Handle S3 URL strings in input by reading from S3Store
  - Reduce handler from ~150 lines to ~40 lines

- [x] **T38.3** Update Batch handler to use LambdaEvent dataclass
  - Apply same simplifications as Lambda handler

- [x] **T38.4** Update state machine to use Context Object
  - Keep InitFlow Pass state (constructs initial input to first step from raw Step Functions input)
  - Add `ItemSelector` to Map state to inject `$$.Execution.Id` and `$$.Execution.Input` into each iteration
  - Add `ResultWriter` to Map state to write aggregation results to S3
  - Add `ResultSelector` to Map state to preserve flow context for aggregation step
  - Update Task states to use consistent `{"input": ..., "flow": {...}}` format

- [ ] **T38.5** Update Lambda handler to extract flow from Context Object
  - Read `$$.Execution.Id` from event (via JsonPath `$$.Execution.Id`)
  - Read `$$.Execution.Input` from event for flow params
  - Handle both direct invocation (with flow in event) and Step Functions invocation (with flow in context)

- [ ] **T38.6** Update manifest format for Map state
  - Use simplified format: `[{"input": "..."}]` (no flow needed - available via Context Object)
  - Update handler to read input from each item's "input" key

- [ ] **T38.7** Write comprehensive unit tests
  - Test LambdaEvent dataclass serialization/deserialization
  - Test handler with various input scenarios (S3 URL, list, dict)
  - Test state machine generation with ItemSelector, ResultWriter, ResultSelector
  - Test map/agg flow end-to-end
  - Test local runner consistency with deployed flow

---

## Summary

| Milestone | Status |
|-----------|--------|
| M1 - Project Scaffolding | Complete |
| M2 - Configuration | Complete |
| M3 - Decorator & Graph Model | Complete |
| M4 - CLI Entry Point | Complete |
| M5 - S3 & Serialisation Layer | Complete |
| M6 - Local Runner | Complete |
| M7 - Runtime Handler | Complete |
| M8 - Lambda Packaging | Complete |
| M9 - State Machine Generation | Complete |
| M10 - CloudFormation Generation | Complete |
| M11 - Build Orchestrator | Complete |
| M12 - End-to-End & Hardening | Complete |
| M13 - Logging & Observability | Complete |
| M14 - Deploy Command | Complete |
| M15 - Local Testing with LocalStack | Complete |
| M16 - Step Functions Local Deployment | Complete |
| M17 - TOML Configuration Format | Complete |
| M18 - Test Coverage Improvements | Complete |
| M19 - CLI Commands: show, logs, destroy | Complete |
| M20 - Flow-level Parameters in .next() | Complete |
| M21 - Flow-level Parameters in .map() and .agg() | Complete |
| M22 - Validate Nested .map() Blocks | Complete |
| M23 - Step Retry Configuration | Complete |
| M24 - Code Refactoring | Complete |
| M25 - Documentation Update | Complete |
| M26 - Type Safety Improvements | Complete |
| M27 - Test Coverage Improvements | Complete |
| M28 - Security Improvements | Complete |
| M29 - CI/CD Setup | Complete |
| M30 - Integration Tests | Complete |
| M31 - Migrate to moto for AWS mocking | Complete |
| M32 - AWS Batch Support | Complete |
| M33 - Map Concurrency Limit | Complete |
| M34 - API Documentation | Complete |
| M35 - Scheduling | Complete |
| M36 - Unify Store Interfaces | Complete |
| M37 - S3 Directory Structure Refactoring | Complete |
| M38 - Lambda Event Dataclass Refactoring | Complete |
| M39 - Distributed Map with ItemSelector/ResultWriter | Complete |

---

## Milestone 40 — Flow Params via Kwargs

_Purpose_: Simplify flow parameter handling by always passing them via `**kwargs`. This removes the silent constraint that flow param names must match function param names, making the API more explicit and less error-prone.

### Background

Currently flow params are passed as explicit kwargs to step functions:
```python
@flow
def my_flow(multiplier=2):
    @step
    def transform(values, mult):  # must match 'multiplier' name exactly
        return [v * mult for v in values]
```

This requires flow param names to match step function param names exactly. With kwargs:
```python
@flow
def my_flow(multiplier=2):
    @step
    def transform(values, **kwargs):  # receives all flow params
        return [v * kwargs["multiplier"] for v in values]
```

### Tasks

- [x] **T40.1** Update decorators to remove explicit kwargs
  - Remove `**kwargs` from `StepNode.next()`
  - Remove `**kwargs` from `StepNode.map()` 
  - Remove `**kwargs` from `StepNode.agg()`

- [x] **T40.2** Update handler to pass flow params via kwargs
  - Remove `_filter_flow_params()` function
  - Always pass flow params as `**kwargs`

- [x] **T40.3** Update runner to pass flow params via kwargs
  - Update `_execute_step()` to pass flow params as `**kwargs`

- [x] **T40.4** Update CI test pipeline example
  - Rewrite step functions to use `**kwargs`

- [x] **T40.5** Update tests
  - Remove tests using explicit kwargs in `.next()`, `.map()`, `.agg()`
  - Add tests for `**kwargs` flow param usage

- [x] **T40.6** Update documentation
  - Document new flow params behavior in docs/design.md

---

## Summary

| Milestone | Status |
|-----------|--------|
| M1 - Project Scaffolding | Complete |
| M2 - Configuration | Complete |
| M3 - Decorator & Graph Model | Complete |
| M4 - CLI Entry Point | Complete |
| M5 - S3 & Serialisation Layer | Complete |
| M6 - Local Runner | Complete |
| M7 - Runtime Handler | Complete |
| M8 - Lambda Packaging | Complete |
| M9 - State Machine Generation | Complete |
| M10 - CloudFormation Generation | Complete |
| M11 - Build Orchestrator | Complete |
| M12 - End-to-End & Hardening | Complete |
| M13 - Logging & Observability | Complete |
| M14 - Deploy Command | Complete |
| M15 - Local Testing with LocalStack | Complete |
| M16 - Step Functions Local Deployment | Complete |
| M17 - TOML Configuration Format | Complete |
| M18 - Test Coverage Improvements | Complete |
| M19 - CLI Commands: show, logs, destroy | Complete |
| M20 - Flow-level Parameters in .next() | Complete |
| M21 - Flow-level Parameters in .map() and .agg() | Complete |
| M22 - Validate Nested .map() Blocks | Complete |
| M23 - Step Retry Configuration | Complete |
| M24 - Code Refactoring | Complete |
| M25 - Documentation Update | Complete |
| M26 - Type Safety Improvements | Complete |
| M27 - Test Coverage Improvements | Complete |
| M28 - Security Improvements | Complete |
| M29 - CI/CD Setup | Complete |
| M30 - Integration Tests | Complete |
| M31 - Migrate to moto for AWS mocking | Complete |
| M32 - AWS Batch Support | Complete |
| M33 - Map Concurrency Limit | Complete |
| M34 - API Documentation | Complete |
| M35 - Scheduling | Complete |
| M36 - Unify Store Interfaces | Complete |
| M37 - S3 Directory Structure Refactoring | Complete |
| M38 - Lambda Event Dataclass Refactoring | Complete |
| M39 - Distributed Map with ItemSelector/ResultWriter | Complete |
| M40 - Flow Params via Kwargs | Complete |
