"""LiveKit LLM adapter for a llama.cpp OpenAI-compatible GGUF server.

There is no Colab or ngrok dependency in this implementation.
"""
import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid

from livekit.agents import llm
from livekit.agents._exceptions import APIConnectionError, APIStatusError
from livekit.agents.llm import ChatChunk, ChoiceDelta
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

from latency_metrics import log_stage

logger = logging.getLogger("voice-agent.llm")


class GGUFLLM(llm.LLM):
    """LiveKit LLM backed by a llama.cpp GGUF server."""

    def __init__(self, base_url: str, timeout: float = 180.0) -> None:
        super().__init__()
        normalized_url = base_url.strip().rstrip("/")
        if not normalized_url.startswith(("http://", "https://")):
            normalized_url = f"http://{normalized_url}"
        self._base_url = normalized_url
        self._timeout = timeout
        self._model = os.getenv("LLM_MODEL", "qwen-urdu")
        self._api_key = os.getenv("LLM_API_KEY", "")

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "llama-cpp-gguf"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls=None,
        tool_choice=None,
        extra_kwargs=None,
    ) -> "GGUFLLMStream":
        return GGUFLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )


class GGUFLLMStream(llm.LLMStream):
    async def _run(self) -> None:
        turn_id = uuid.uuid4().hex[:12]
        turn_started = time.perf_counter()
        messages = []

        for item in self._chat_ctx.items:
            if getattr(item, "type", None) != "message":
                continue
            text = item.text_content
            if text and item.role in ("system", "user", "assistant"):
                messages.append({"role": item.role, "content": text})

        if not any(message["role"] == "user" for message in messages):
            raise APIStatusError(
                message="No user message was available for GGUF inference",
                status_code=400,
                retryable=False,
            )

        payload = {
            "model": self._llm._model,
            "messages": messages,
            "stream": False,
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "120")),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._llm._api_key:
            headers["Authorization"] = f"Bearer {self._llm._api_key}"

        base_url = self._llm._base_url
        if base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")

        def _request() -> dict:
            with urllib.request.urlopen(request, timeout=self._llm._timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        started = time.perf_counter()
        try:
            result = await asyncio.to_thread(_request)
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise APIStatusError(
                message=response_body,
                status_code=exc.code,
                retryable=exc.code >= 500,
            ) from exc
        except Exception as exc:
            raise APIConnectionError() from exc

        try:
            reply = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise APIStatusError(
                message=f"Invalid llama.cpp response: {result}",
                status_code=502,
                retryable=True,
            ) from exc

        response_ms = (time.perf_counter() - started) * 1000
        log_stage(
            "external_llm_api_complete",
            response_ms,
            turn_id=turn_id,
            buffered=True,
            output_chars=len(reply),
        )
        log_stage("llm_first_token_visible", response_ms, turn_id=turn_id, buffered=True)
        self._event_ch.send_nowait(
            ChatChunk(
                id=f"gguf-{turn_id}",
                delta=ChoiceDelta(role="assistant", content=reply),
            )
        )
        log_stage(
            "llm_turn_total",
            (time.perf_counter() - turn_started) * 1000,
            turn_id=turn_id,
        )
