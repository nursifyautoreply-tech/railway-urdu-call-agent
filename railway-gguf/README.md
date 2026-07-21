# Railway GGUF model server

This directory deploys a private Hugging Face GGUF model on Railway using
llama.cpp's OpenAI-compatible server.

Keep Railway's build root at the repository root and select this file with
`RAILWAY_DOCKERFILE_PATH=/railway-gguf/Dockerfile`.

## Required Railway variables

- `HF_REPO`: `Talha44220/qwen35-4b-urdu-gguf`
- `HF_FILE`: `qwen3.5-4b.Q4_K_M.gguf`
- `HF_TOKEN`: Fine-grained, read-only Hugging Face token for the private repo

## Optional Railway variables

- `MODEL_ALIAS=qwen-urdu`
- `CTX_SIZE=2048`
- `THREADS=4`
- `PARALLEL=1`
- `RAILWAY_HEALTHCHECK_TIMEOUT_SEC=600`
- `LLAMA_CACHE=/models`

Attach a Railway volume at `/models` when using `LLAMA_CACHE=/models`.

Configure `/health` as the Railway health-check path. After deployment,
generate a public domain and open its root URL for the llama.cpp chat UI.
The OpenAI-compatible chat endpoint is `/v1/chat/completions`.
