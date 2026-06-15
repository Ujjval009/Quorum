#!/usr/bin/env bash
set -euo pipefail

# Eval Suite Runner
# =================
# Usage:
#   ./scripts/run_eval_suite.sh              # full suite (needs Groq)
#   EVAL_SKIP_LLM=1 ./scripts/run_eval_suite.sh  # skip LLM narrative checks
#
# Environment:
#   EVAL_API_URL   — backend URL (default http://localhost:8000)
#   EVAL_EMAIL     — login email (default evaluser@quorum.ai)
#   EVAL_PASSWORD  — login password (default EvalPass123!)
#   EVAL_SKIP_LLM  — set to 1 to skip LLM narrative checks
#   EVAL_MAX_RETRIES — max retries on rate limit (default 3)

cd "$(dirname "$0")/.."

export EVAL_API_URL="${EVAL_API_URL:-http://localhost:8000}"
export EVAL_SKIP_LLM="${EVAL_SKIP_LLM:-0}"
export EVAL_MAX_RETRIES="${EVAL_MAX_RETRIES:-3}"

echo "=== Eval Suite ==="
echo "  API URL:       $EVAL_API_URL"
echo "  Skip LLM:      $EVAL_SKIP_LLM"
echo "  Max Retries:   $EVAL_MAX_RETRIES"
echo ""

uv run pytest tests/eval_suite.py -v -m eval "$@"
