#!/usr/bin/env bash
#
# ZugaLife Start — boots backend + frontend.
#
# Usage: bash start.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# Ensure data directory exists for SQLite
mkdir -p backend/data

echo "Starting ZugaLife..."
echo ""
echo "  Backend:   http://localhost:8001"
echo "  Frontend:  http://localhost:5174"
echo ""
echo "  Press Ctrl+C to stop both."
echo ""

# Start backend in background
(cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload) &
BACKEND_PID=$!

# Give backend a moment to initialize
sleep 2

# Start frontend in foreground (Ctrl+C stops this, then we clean up backend)
trap "kill $BACKEND_PID 2>/dev/null; echo ''; echo 'Stopped.'; exit 0" INT TERM
(cd frontend && npm run dev)

# If frontend exits, also stop backend
kill $BACKEND_PID 2>/dev/null
