# AGENTS.md - Development Guidelines for lokki (lokkiflow pypi package)

## Getting Started

Before working on the codebase, read:
- **README.md** - Project overview, quickstart, and usage examples
- **docs/*.md** - Spec files with requirements, design, and tasks

## Requirements

- **Python**: 3.13+ (required for `tomllib` stdlib module)

## Tools

Only use these tools: bash, read, glob, grep, edit, write, task, webfetch, todowrite, question.

## Taskfile

Common development tasks are defined in `Taskfile.yaml`. **Always use `task version:bump`** before testing examples with deployments.

```bash
# List available tasks
task --list

# Common tasks
task dev:start         # Start LocalStack, pypiserver, registry
task dev:stop         # Stop containers
task test             # Run all unit tests
task lint             # Run ruff linter
task format           # Format code with ruff
task version:bump     # Bump patch version (ALWAYS run before testing examples)
task publish:pypiserver  # Publish to local pypiserver
```

## Development Commands

> **Important**: Always run `task version:bump` before testing examples with deployments!

```bash
uv sync                      # Install dependencies
uv run pytest                # Run all tests
uv run ruff check lokki/    # Linting
uv run ruff format lokki/   # Formatting
python flow_script.py run   # Run locally
python flow_script.py build # Build artifacts
```

## Local Development with LocalStack

Before testing deployment-related commands, ensure LocalStack, pypiserver, and registry are running:

```bash
# Check if Docker is running
docker ps

# Start services (using task)
task dev:start

# Verify services are running
docker ps
```

Services required:
- **LocalStack** (port 4566) - AWS mock for S3, Step Functions, Lambda, CloudFormation
- **pypiserver** (port 8080) - Local Python package index
- **registry:ci** (port 5000) - Local Docker registry for Lambda container images

### Testing with Examples

When testing with example projects:

1. **Publish new lokkiflow version to pypiserver:**
   ```bash
   task publish:pypiserver
   ```

2. **Sync example project:**
   ```bash
   cd examples/weather
   uv sync
   ```

3. **Run deployment commands:**
   ```bash
   python flow.py run   # Run locally
   python flow.py build # Build artifacts
   python flow.py deploy --confirm  # Deploy to LocalStack
   python flow.py invoke --param1 value1  # Invoke deployed flow
   python flow.py show   # Show executions (requires real AWS)
   python flow.py logs   # Fetch logs (requires real AWS)
   python flow.py destroy --confirm  # Destroy stack
   ```

Note: `show` and `logs` commands require real AWS or LocalStack with full service support.
Note: Lambda Container Images and AWS Batch require LocalStack Pro. Use ZIP package type for Community edition testing.

### Testing Docker Images

Docker image tests verify that Lambda container images work correctly. Tests auto-detect Docker and skip if not available.

```bash
# Run Docker image tests (auto-detects Docker)
pytest tests/test_docker_images.py -v
```

Tests:
1. Build Docker image with pandas dependency
2. Verify pandas is installed in the image

## Agent Workflow

1. Test locally before building: `python flow_script.py run`
2. After completing a milestone, bump the minor version in pyproject.toml
3. Write tests for each task (see Mandatory Unit Testing below)
4. Ensure all tests pass before marking a task complete

## Git Workflow

- **Branches**: Create feature branches using format `feature/<snake_cased_feature_name>`
  - Example: `feature/add_toml_config`, `feature/remove_yaml_dependency`
- **Commits**: Do NOT create commits - only create branches
- **Clean repo check**: Before creating a branch, verify there are no pending changes
  - If there are local changes, inform the user and ask how to proceed
- **Security**: Never commit secrets, credentials, or sensitive data

## Mandatory Unit Testing

- Create `tests/test_<module>.py` for each task
- Test normal behavior, edge cases, and error conditions
- Run: `uv run pytest tests/test_<module>.py -v`

## Testing Patterns

- Use `pytest` as the test framework
- Use `pytest.MonkeyPatch` for environment variable mocking
- Use `tmp_path` fixture for temporary file/directory operations
- Group tests by class following `Test<ClassName>` convention
- Example test structure:

```python
class TestClassName:
    def test_normal_behavior(self) -> None:
        # Arrange
        ...
        # Act
        ...
        # Assert
        ...

    def test_edge_case(self) -> None:
        ...

    def test_error_condition(self) -> None:
        with pytest.raises(ExpectedException):
            ...
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `LOKKI_ARTIFACT_BUCKET` | S3 bucket for pipeline data |
| `LOKKI_IMAGE_REPOSITORY` | Docker repository (`registry:ci` for local, or ECR prefix) |
| `LOKKI_AWS_REGION` | AWS region for deployments |
| `LOKKI_AWS_ENDPOINT` | AWS endpoint for local development |
| `LOKKI_BUILD_DIR` | Output directory for build artifacts |
| `LOKKI_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Documentation

| File | Purpose |
|------|---------|
| README.md | Project overview, quickstart, and usage examples |
| docs/api.md | API reference for decorators, CLI, and configuration |
| docs/config.md | Complete configuration reference |
| docs/requirements.md | User requirements and configuration reference |
| docs/design.md | Architecture and implementation details |
| docs/tasks.md | Planned milestones |
| docs/tasks-completed.md | Completed milestones |
