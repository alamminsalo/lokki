# AGENTS.md - Development Guidelines for lokki

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
| `LOKKI_AWS_ENDPOINT` | AWS endpoint for local development |
| `LOKKI_BUILD_DIR` | Output directory for build artifacts |
| `LOKKI_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Documentation

| File | Purpose |
|------|---------|
| docs/requirements.md | User requirements and configuration reference |
| docs/design.md | Architecture and implementation details |
| docs/tasks.md | Planned milestones |
| docs/tasks-completed.md | Completed milestones |
