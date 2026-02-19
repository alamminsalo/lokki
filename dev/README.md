# Development Tools

This directory contains tools for local development and testing.

## Services

### LocalStack
Full local AWS stack for testing deployment.

### PyPI Server
Local PyPI server for testing package installation in Lambda containers.

## Quick Start

```bash
# Start all services
docker-compose up -d

# Wait for services to be ready (check health)
docker-compose ps

# Publish lokki to local PyPI
./publish.sh

# Or with custom host
PYPI_HOST=localhost:8080 ./publish.sh
```

## Usage

### 1. Start services
```bash
cd dev
docker-compose up -d
```

### 2. Publish lokki to local PyPI
```bash
./publish.sh
```

### 3. Configure your flow project
Add lokki to your flow project's `pyproject.toml` with the local PyPI index:

```toml
[project]
name = "my-flow"
version = "0.1.0"
dependencies = [
    "lokki",
]

[tool.pip]
# Use local PyPI for development
extra-index-url = http://localhost:8080/simple
```

Then build and deploy:
```bash
python flow_script.py build
python flow_script.py deploy
```

## Alternative: Path-based development

For development without a local PyPI server, use a path reference:

```toml
[project]
dependencies = [
    "lokki@../lokki",
]
```

Note: This requires the path to be accessible during Docker build (e.g., via a volume mount).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYPI_HOST` | `localhost:8080` | PyPI server host:port |

## Configuration

Make sure your `lokki.yml` has the correct settings for LocalStack:

```yaml
aws:
  artifact_bucket: lokki-artifacts
  endpoint: http://localhost:4566
  ecr_repo_prefix: ""  # Use local Docker images

lambda:
  timeout: 60
  memory: 256
  image_tag: latest
  env:
    LOG_LEVEL: DEBUG
```

## Notes

- LocalStack's S3 endpoint: `http://localhost:4566`
- When using local Docker images (empty `ecr_repo_prefix`), Lambda functions will use local image names
- The Lambda runtime inside containers needs to reach the PyPI server at `host.docker.internal:8080`
