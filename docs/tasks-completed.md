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
    └── handler.py           # Lambda handler wrapper
```

### T1.3 — Write lokki/__init__.py ✅
- Exports public API: `flow`, `step`
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

### T2.5 — Unit tests
- Not yet implemented (test framework pending)

---

## Summary

**Completed:** T1.1, T1.2, T1.3, T2.1, T2.2, T2.3, T2.4

**Pending:** T2.5 (tests), Milestone 3+ (decorators, graph, CLI, S3, runner, etc.)

## Next Steps

1. Implement Milestone 3 — Decorator & Graph Model (StepNode, MapBlock, FlowGraph)
2. Implement Milestone 4 — CLI Entry Point
3. Add unit tests for config module
4. Run `uv sync` to install dependencies
