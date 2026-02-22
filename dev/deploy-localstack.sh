#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

LOCALSTACK_HOST="${LOCALSTACK_HOST:-localhost}"
LOCALSTACK_PORT="${LOCALSTACK_PORT:-4566}"
ENDPOINT_URL="http://${LOCALSTACK_HOST}:${LOCALSTACK_PORT}"

FLOW_FILE="${FLOW_FILE:-$PROJECT_DIR/examples/weather/weather.py}"
CONFIG_FILE="${CONFIG_FILE:-$PROJECT_DIR/examples/weather/lokki.toml}"

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

STACK_NAME="lokki-test"
FLOW_NAME="birds-flow"
BUILD_DIR="$PROJECT_DIR/examples/lokki-build"

echo "=== Deploying to LocalStack ==="
cd "$PROJECT_DIR/examples"
uv run python -c "
from pathlib import Path
from lokki.deploy import Deployer
from lokki.config import load_config

config = load_config()
deployer = Deployer(
    stack_name='$STACK_NAME',
    region='us-east-1',
    endpoint='$ENDPOINT_URL',
    package_type=config.lambda_cfg.package_type
)

deployer.deploy(
    flow_name='$FLOW_NAME',
    artifact_bucket='lokki',
    ecr_repo_prefix='',
    build_dir=Path('$BUILD_DIR'),
    aws_endpoint='$ENDPOINT_URL',
    package_type=config.lambda_cfg.package_type
)
"

echo "=== Done! ==="
echo "Stack '$STACK_NAME' deployed to LocalStack"
echo "Access LocalStack at: $ENDPOINT_URL"
