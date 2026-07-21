# End-to-end Railway call deployment

Deploy four Railway services from the same GitHub repository:

1. `gguf-model` - Dockerfile `/railway-gguf/Dockerfile`
2. `voice-agent` - Dockerfile `/railway-gguf/Dockerfile.voice`
3. `dashboard` - Dockerfile `/railway-gguf/Dockerfile.dashboard`
4. Railway MongoDB database

Keep the repository root as the build context for all three source services.
Select each Dockerfile with the Railway service variable
`RAILWAY_DOCKERFILE_PATH`.

## gguf-model variables

```text
RAILWAY_DOCKERFILE_PATH=/railway-gguf/Dockerfile
HF_REPO=Talha44220/qwen35-4b-urdu-gguf
HF_FILE=qwen3.5-4b.Q4_K_M.gguf
HF_TOKEN=hf_read_only_token
MODEL_ALIAS=qwen-urdu
CTX_SIZE=2048
THREADS=4
PARALLEL=1
LLAMA_CACHE=/models
RAILWAY_HEALTHCHECK_TIMEOUT_SEC=600
```

Attach a volume at `/models`, set the health check to `/health`, and generate
a public domain temporarily for browser/API testing.

## voice-agent variables

```text
RAILWAY_DOCKERFILE_PATH=/railway-gguf/Dockerfile.voice
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
DEEPGRAM_API_KEY=...
LLM_BASE_URL=http://gguf-model.railway.internal:8080
LLM_MODEL=qwen-urdu
LLM_MAX_TOKENS=120
LLM_TEMPERATURE=0.7
DASHBOARD_WEBHOOK_URL=http://dashboard.railway.internal:8000/webhook/call-summary
```

Set `PORT=8080` on `gguf-model` and `PORT=8000` on `dashboard` so the private
URLs use stable ports. The voice agent is a worker and does not need a public
domain.

## dashboard variables

```text
RAILWAY_DOCKERFILE_PATH=/railway-gguf/Dockerfile.dashboard
PORT=8000
MONGODB_URI=${{MongoDB.MONGO_URL}}
SLACK_WEBHOOK_URL=
```

Use Railway's variable picker for the MongoDB connection reference; its exact
service and variable names depend on the database Railway creates.
