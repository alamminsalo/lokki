#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

LOCALSTACK_HOST="${LOCALSTACK_HOST:-localhost}"
LOCALSTACK_PORT="${LOCALSTACK_PORT:-4566}"
ENDPOINT_URL="http://${LOCALSTACK_HOST}:${LOCALSTACK_PORT}"

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
spec = importlib.util.spec_from_file_location('flow', 'birds_flow_example.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

from lokki.builder.builder import Builder
from lokki.config import load_config

graph = module.birds_flow()
config = load_config()
Builder.build(graph, config)
"

cd lokki-build

echo "=== Testing Lambda with SAM local ==="
echo ""
echo "Invoking get_birds function..."
sam local invoke GetBirdsFunction \
    --event '{"test": true}' \
    --endpoint-url "http://127.0.0.1:3001" \
    2>/dev/null || echo "SAM local not running, trying direct invoke..."

echo ""
echo "To test with SAM local Lambda endpoint:"
echo "1. In one terminal: cd lokki-build && sam local start-lambda --port 3001"
echo "2. In another: sam local invoke GetBirdsFunction --endpoint-url http://127.0.0.1:3001"
echo ""
echo "To test individual steps, run:"
echo "  cd lokki-build"
echo "  sam local invoke GetBirdsFunction"
echo "  sam local invoke UppercaseListFunction --event '{\"result_url\": \"file:///tmp/test.pkl\"}'"