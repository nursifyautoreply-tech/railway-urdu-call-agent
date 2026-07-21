#!/bin/sh
set -eu

: "${HF_REPO:?HF_REPO is required (example: username/model-repo)}"
: "${HF_FILE:?HF_FILE is required (example: model-Q4_K_M.gguf)}"
: "${HF_TOKEN:?HF_TOKEN is required for the private Hugging Face repository}"

exec /app/llama-server \
  --hf-repo "$HF_REPO" \
  --hf-file "$HF_FILE" \
  --alias "${MODEL_ALIAS:-qwen-urdu}" \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --ctx-size "${CTX_SIZE:-2048}" \
  --threads "${THREADS:-4}" \
  --parallel "${PARALLEL:-1}" \
  --jinja
