#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

LOCALSTACK_HOST="${LOCALSTACK_HOST:-localhost}"
LOCALSTACK_PORT="${LOCALSTACK_PORT:-4566}"
ENDPOINT_URL="http://${LOCALSTACK_HOST}:${LOCALSTACK_PORT}"

FLOW_FILE="${FLOW_FILE:-$PROJECT_DIR/examples/birds_flow_example.py}"
CONFIG_FILE="${CONFIG_FILE:-$PROJECT_DIR/examples/lokki.yml}"

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

echo "=== Waiting for LocalStack to be ready ==="
until curl -s "$ENDPOINT_URL/_localstack/health" > /dev/null 2>&1; do
    echo "Waiting for LocalStack..."
    sleep 2
done
echo "LocalStack is ready"

echo "=== Creating S3 bucket ==="
aws --endpoint-url="$ENDPOINT_URL" s3api create-bucket --bucket lokki 2>/dev/null || true

echo "=== Building flow ==="
cd "$PROJECT_DIR/examples"
rm -rf lokki-build/
uv run python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('flow', '$FLOW_FILE')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

from lokki.builder.builder import Builder
from lokki.config import load_config

graph = module.birds_flow()
config = load_config()
Builder.build(graph, config)
"

echo "=== Build complete! ==="
echo "Artifacts written to: $PROJECT_DIR/examples/lokki-build/"
echo ""
echo "Note: CloudFormation deployment to LocalStack requires ZIP-based Lambda functions."
echo "LocalStack does not fully support container image-based Lambdas (PackageType: Image)."
echo ""
echo "To test the flow locally, run:"
echo "  cd examples && uv run python birds_flow_example.py run"
