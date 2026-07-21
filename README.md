# Railway voice agent deployment bundle

This bundle deploys the existing Urdu telephone agent without Colab or ngrok.
The GGUF is downloaded from the private Hugging Face repository at runtime.

Deploy three source services from this repository and add one Railway MongoDB
database:

1. `gguf-model`: `RAILWAY_DOCKERFILE_PATH=/railway-gguf/Dockerfile`
2. `voice-agent`: `RAILWAY_DOCKERFILE_PATH=/railway-gguf/Dockerfile.voice`
3. `dashboard`: `RAILWAY_DOCKERFILE_PATH=/railway-gguf/Dockerfile.dashboard`
4. MongoDB: create through Railway's database menu

Keep the Railway root directory at `/` for all source services. Complete
variables and deployment instructions are in
`railway-gguf/FULL_CALL_DEPLOYMENT.md`.

Never commit `.env` files or real API tokens. Store `HF_TOKEN`, LiveKit keys,
the Deepgram key, and other credentials in Railway service variables.
