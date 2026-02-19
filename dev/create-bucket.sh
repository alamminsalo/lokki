#!/bin/bash

aws --endpoint-url=http://${LOCALSTACK_HOST:-localhost}:4566 \
  s3api create-bucket --bucket lokki
