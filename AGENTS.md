# AGENTS.md - Development Guidelines for lokki (lokkiflow pypi package)

## Getting Started

Before working on the codebase, read:
- **README.md** - Project overview, quickstart, and usage examples
- **docs/*.md** - Spec files with requirements, design, and tasks

## Requirements

- **Python**: 3.13+ (required for `tomllib` stdlib module)

## Tools

Only use these tools: bash, read, glob, grep, edit, write, task, webfetch, todowrite, question.

## Development Commands

```bash
uv sync                      # Install dependencies
uv run pytest                # Run all tests
uv run ruff check lokki/    # Linting
uv run ruff format lokki/   # Formatting
python flow_script.py run   # Run locally
python flow_script.py build # Build artifacts
```

## Local Development with LocalStack

Before testing deployment-related commands, ensure LocalStack and pypiserver are running:

```bash
# Check if Docker is running
docker ps

# Start LocalStack and pypiserver (if not running)
docker compose up -d

# Verify services are running
docker ps
```

Services required:
- **LocalStack** (port 4566) - AWS mock for S3, Step Functions, Lambda, CloudFormation
- **pypiserver** (port 8080) - Local Python package index

### Testing with Examples

When testing with example projects:

1. **Bump version and publish lokkiflow to pypiserver:**
   ```bash
   # Edit pyproject.toml - bump version number (e.g., 0.3.0 -> 0.3.1)
   # Build the package
   uv build
   # Upload to local pypiserver (no auth required)
   uv run python -m twine upload --repository-url http://localhost:8080 dist/* -u "" -p ""
   # Update the example project packages to get the newest version
   # cd example/<example>
   uv sync --upgrade
   ```

2. **Update example project to use new version:**
   ```bash
   # Edit examples/weather/pyproject.toml - update lokkiflow version constraint
   cd examples/weather
   uv sync
   ```

3. **Run deployment commands:**
   ```bash
   python weather.py run   # Run locally
   python weather.py build # Build artifacts
   python weather.py deploy --confirm  # Deploy to LocalStack
   python weather.py show   # Show executions (requires real AWS)
   python weather.py logs   # Fetch logs (requires real AWS)
   python weather.py destroy --confirm  # Destroy stack
   ```

Note: `show` and `logs` commands require real AWS or LocalStack with full service support.

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
| `LOKKI_IMAGE_REPOSITORY` | Docker repository (local, docker.io, or ECR prefix) |
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
