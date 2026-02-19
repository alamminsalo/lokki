#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

PYPI_HOST="${PYPI_HOST:-localhost:8080}"
PACKAGE_DIR="$PROJECT_DIR/dist"

echo "=== Building lokki package ==="
cd "$PROJECT_DIR"
rm -rf dist/
uv build

echo "=== Publishing to local PyPI ($PYPI_HOST) ==="
twine upload --repository-url "http://$PYPI_HOST" dist/*

echo "=== Done! ==="
echo "To install from local PyPI, add to your Dockerfile:"
echo "  RUN pip install --index-url http://$PYPI_HOST/simple lokki"
