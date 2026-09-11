#!/bin/sh
# Run on the development PC. Output: frontend/dist -> copy to the capture PC.
cd "$(dirname "$0")" && DOCKER_BUILDKIT=1 docker build --target export --output type=local,dest=dist .
