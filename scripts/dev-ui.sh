#!/bin/sh
# Vite dev server with live reload on http://localhost:5173.
# The backend must already be running (scripts/sim-backend.sh, or a real capture PC):
#   BACKEND=http://192.168.1.10:8000 scripts/dev-ui.sh
set -e
cd "$(dirname "$0")/../frontend"
docker run --rm -it --network host -v "$PWD":/app -v /app/node_modules -w /app \
  -e BACKEND="${BACKEND:-http://localhost:8000}" node:20-alpine \
  sh -c "npm install --no-audit --no-fund && npm run dev -- --host 0.0.0.0"
