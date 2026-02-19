# AGENTS.md - Development Guidelines for lokki

## Build/Test/Run Commands

```bash
# Install dependencies
uv sync

# Run a single test file
uv run pytest tests/test_runner.py          # specific test file
uv run pytest tests/test_runner.py::test_map  # specific test function

# Run all tests
uv run pytest

# Run type checking
uv run mypy lokki/

# Run linting
uv run ruff check lokki/

# Fix linting issues
uv run ruff check lokki/ --fix

# Format code
uv run ruff format lokki/

# Run locally (for flow scripts)
python flow_script.py run

# Build deployment artifacts
python flow_script.py build
```

## Code Style Guidelines

### Imports
- Standard library imports first, then third-party, then local imports (separated by blank lines)
- Use absolute imports: `from lokki.decorators import step`
- Group related imports together
- Avoid wildcards: `from module import *`

### Formatting
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 88 characters (ruff default)
- Use double quotes for strings
- Trailing commas in multi-line structures
- One logical statement per line

### Type Hints
- Use Python 3.13+ type hint syntax
- Always annotate function parameters and return types
- Use `Optional[T]` or `T | None` for nullable types
- Use `Callable[[ArgType], ReturnType]` for function types
- Prefer explicit types over `Any`

### Naming Conventions
- **Classes**: PascalCase (`StepNode`, `FlowGraph`, `MapBlock`)
- **Functions/Methods**: snake_case (`get_birds`, `make_handler`)
- **Constants**: UPPER_SNAKE_CASE (`LOKKI_S3_BUCKET`)
- **Private members**: Leading underscore (`_resolve`, `_default_args`)
- **Variables**: Descriptive snake_case names

### Error Handling
- Raise specific exceptions (`ValueError`, `TypeError`) with clear messages
- Use custom exception classes for domain-specific errors
- Wrap external library exceptions at boundaries
- Fail fast with descriptive error messages

### Documentation
- Use docstrings for public modules, classes, and functions
- Follow Google or NumPy docstring style consistently
- Include type hints in docstrings only when needed for clarity

## Architecture Notes

- `lokki/decorators.py`: `@step` and `@flow` decorators, `StepNode`, `MapBlock`
- `lokki/graph.py`: `FlowGraph` execution graph model
- `lokki/runner.py`: Local execution engine
- `lokki/builder/`: Build pipeline (lambda_pkg, state_machine, cloudformation)
- `lokki/runtime/`: Lambda handler wrapper (runs in production)
- `lokki/s3.py`: S3 read/write with gzip pickle serialization
- `lokki/config.py`: Configuration loading from `lokki.yml`

## Key Patterns

- **Decorator pattern**: Steps are registered, not executed at definition time
- **Chain of responsibility**: `.map()` returns `MapBlock`, `.agg()` closes and returns `StepNode`
- **S3 abstraction**: Steps receive/return plain Python objects; serialization is transparent
- **Data passing**: Step Functions pass S3 URLs, not payloads (stays under 256KB limit)

## Configuration

- Global config: `~/.lokki/lokki.yml`
- Local config: `./lokki.yml` (overrides global)
- Environment overrides: `LOKKI_ARTIFACT_BUCKET`, `LOKKI_ECR_REPO_PREFIX`, `LOKKI_BUILD_DIR`
- Lambda runtime env: `LOKKI_S3_BUCKET`, `LOKKI_FLOW_NAME`

### lokki.yml Schema

```yaml
artifact_bucket: my-lokki-artifacts
roles:
  pipeline: arn:aws:iam::123456789::role/lokki-stepfunctions-role
  lambda: arn:aws:iam::123456789::role/lokki-lambda-execution-role
lambda_env:
  LOG_LEVEL: INFO
ecr_repo_prefix: 123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject
build_dir: lokki-build
lambda_defaults:
  timeout: 900
  memory: 512
  image_tag: latest
```

## AI Assistant Rules

- No Cursor or Copilot rules currently defined
- Follow existing code conventions when adding new files
- Keep functions small and focused
- Prefer composition over inheritance
- Test locally with `python flow_script.py run` before building

### Mandatory Unit Testing

**For each task completed, you MUST:**

1. Create a unit test file in `tests/` directory (e.g., `tests/test_config.py`, `tests/test_decorators.py`)
2. Write comprehensive tests covering:
   - Normal/expected behavior
   - Edge cases and error conditions
   - All public functions and classes
3. Run the tests immediately after writing:
   ```bash
   uv run pytest tests/test_<module>.py -v
   ```
4. Ensure all tests pass before marking a task complete
5. If tests fail, fix the code or tests until they pass

**Test file naming convention:** `tests/test_<module>.py`

**Run commands:**
```bash
# Run all tests
uv run pytest

# Run single test file
uv run pytest tests/test_config.py -v

# Run specific test function
uv run pytest tests/test_config.py::test_deep_merge -v

# Run with coverage
uv run pytest --cov=lokki
```

## Repository Structure

```
lokki/
├── lokki/
│   ├── __init__.py              # Public API: exports flow, step
│   ├── decorators.py            # @step and @flow decorator implementations
│   ├── graph.py                 # StepNode, FlowGraph — execution graph model
│   ├── runner.py                # Local execution engine
│   ├── builder/
│   │   ├── builder.py           # Orchestrates the full build
│   │   ├── lambda_pkg.py        # Generates per-step Dockerfile directories
│   │   ├── state_machine.py     # Generates Step Functions JSON
│   │   └── cloudformation.py    # Generates CloudFormation YAML
│   ├── runtime/
│   │   └── handler.py           # Lambda handler wrapper (runs in Lambda)
│   ├── s3.py                    # S3 read/write with gzip pickle
│   └── config.py                # Configuration loading
├── pyproject.toml
├── uv.lock
└── docs/
```

## Dependencies

| Dependency | Role |
|---|---|
| `uv` | Dependency management and venv tooling |
| `stepfunctions` | AWS Step Functions SDK |
| `boto3` | AWS SDK for S3 and Step Functions |
| `pyyaml` | Parsing `lokki.yml` configuration |

## Build Output Structure

```
lokki-build/
├── lambdas/<step_name>/  # One per @step
│   ├── Dockerfile
│   └── handler.py
├── statemachine.json
└── template.yaml
```
