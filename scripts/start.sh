#!/usr/bin/env bash
# One-click launcher for prompt-gen (POSIX / macOS / Linux / Git Bash).
# Usage: bash scripts/start.sh    or   ./scripts/start.sh
# On first run it creates .venv and installs the global `prompt-gen` command.
set -euo pipefail
# This script lives in <repo>/scripts; the project root is its parent.
cd "$(dirname "$0")/.."

PY="$(command -v python3 || command -v python)"

if [ ! -x ".venv/bin/python" ]; then
  echo "No .venv found, creating virtual environment..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -e ".[dev]"
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Please edit it and set DEEPSEEK_API_KEY."
fi

echo
echo "Starting prompt-gen..."
echo

# Delegate to bin/prompt-gen: installs the global command and launches.
exec bin/prompt-gen "$@"
