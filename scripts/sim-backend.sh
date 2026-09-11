#!/bin/sh
# Runs the backend in simulation mode inside Docker: no cameras needed.
# FFmpeg test sources stand in for the RTSP streams. Open http://localhost:8000
# (after building the dashboard) or use scripts/dev-ui.sh for live reload.
set -e
cd "$(dirname "$0")/.."
mkdir -p .sim
[ -f .sim/config.json ] || printf '{\n  "simulate": true,\n  "data_dir": "/app/.sim/data",\n  "min_free_disk_gb": 1\n}\n' > .sim/config.json
docker run --rm -it -p 8000:8000 -v "$PWD":/app -w /app -e AID4SME_CONFIG=/app/.sim/config.json \
  python:3.8-slim sh -c "apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null && \
  pip install -q -r requirements.txt && python run_server.py --simulate"
