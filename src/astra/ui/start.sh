#!/usr/bin/env bash
set -e

echo "=== ASTRA UI Launcher ==="
echo "Starting backend (uvicorn) and frontend (npm) in parallel..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

cleanup() {
  echo "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "Starting FastAPI backend on port 8000..."
cd "$BACKEND_DIR"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "Starting React frontend on port 3000..."
cd "$FRONTEND_DIR"
npm start &
FRONTEND_PID=$!

echo ""
echo "ASTRA UI running:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both servers."
echo ""

wait
