"""Gayatri AI — Google Gemini provider.

Uses the Gemini API: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

from core.providers.base import (
    Capability,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    LLMProvider,
    ModelInfo,
    SpeedTier,
)

logger = logging.getLogger("gayatri.providers.google")

_KNOWN_MODELS: dict[str, dict] = {
    "gemini-2.0-flash": {"name": "Gemini 2.0 Flash", "ctx": 1000000, "speed": SpeedTier.FAST, "tools": True, "vision": True, "json": True},
    "gemini-2.0-flash-lite": {"name": "Gemini 2.0 Flash Lite", "ctx": 1000000, "speed": SpeedTier.FAST, "tools": True, "vision": True, "json": True},
    "gemini-1.5-pro": {"name": "Gemini 1.5 Pro", "ctx": 2000000, "speed": SpeedTier.MEDIUM, "tools": True, "vision": True, "json": True},
    "gemini-1.5-flash": {"name": "Gemini 1.5 Flash", "ctx": 1000000, "speed": SpeedTier.FAST, "tools": True, "vision": True, "json": True},
    "gemini-1.0-pro": {"name": "Gemini 1.0 Pro", "ctx": 32000, "speed": SpeedTier.MEDIUM, "tools": True, "vision": False, "json": True},
}


class GoogleProvider(LLMProvider):
    """Google Gemini API provider.

    Uses generateContent endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._name = "Google"
        self._key = "google"
        self._models: list[ModelInfo] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def key(self) -> str:
        return self._key

    def _base_url(self) -> str:
        return "https://generativelanguage.googleapis.com/v1beta"

    def validate_key(self) -> tuple[bool, str]:
        """Validate key by calling list models endpoint."""
        try:
            import httpx
            response = httpx.get(
                f"{self._base_url()}/models?key={self._api_key}",
                timeout=10.0,
            )
            if response.status_code == 200:
                return True, "OK"
            elif response.status_code == 400:
                return False, "Invalid API key"
            else:
                return False, f"HTTP {response.status_code}"
        except ImportError:
            return False, "httpx not installed"
        except Exception as exc:
            return False, str(exc)[:200]

    def list_models(self) -> list[ModelInfo]:
        """Fetch models from Google API, with known model fallbacks."""
        if self._models is not None:
            return self._models

        self._models = []
        try:
            import httpx
            response = httpx.get(
                f"{self._base_url()}/models?key={self._api_key}",
                timeout=15.0,
            )
            if response.status_code == 200:
                data = response.json()
                for m in data.get("models", []):
                    mid = m.get("name", "").replace("models/", "")
                    if "gemini" not in mid.lower():
                        continue
                    known = _KNOWN_MODELS.get(mid, {})
                    self._models.append(ModelInfo(
                        id=mid,
                        name=known.get("name", m.get("displayName", mid)),
                        provider="google",
                        context_length=known.get("ctx", 8192),
                        speed_tier=known.get("speed", SpeedTier.MEDIUM),
                        capabilities=[Capability.CHAT, Capability.STREAM, Capability.SYSTEM_PROMPT],
                        supports_tools=known.get("tools", False),
                        supports_vision=known.get("vision", False),
                        supports_json=known.get("json", False),
                    ))
        except Exception as exc:
            logger.error(f"Failed to fetch Google models: {exc}")

        # Fallback to known models
        if not self._models:
            for mid, meta in _KNOWN_MODELS.items():
                self._models.append(ModelInfo(
                    id=mid,
                    name=meta["name"],
                    provider="google",
                    context_length=meta.get("ctx", 8192),
                    speed_tier=meta.get("speed", SpeedTier.MEDIUM),
                    capabilities=[Capability.CHAT, Capability.STREAM, Capability.SYSTEM_PROMPT],
                    supports_tools=meta.get("tools", False),
                    supports_vision=meta.get("vision", False),
                    supports_json=meta.get("json", False),
                ))

        return self._models

    def _convert_messages(self, messages: list[ChatMessage], supports_system: bool = True) -> tuple[str | None, list[dict]]:
        """Convert ChatMessages to Gemini format.

        Gemini uses 'user'/'model' roles. System prompt goes in systemInstruction.
        Returns (system_prompt, contents_list).
        """
        system_prompt = None
        contents = []

        for msg in messages:
            if msg.role == "system":
                if supports_system:
                    system_prompt = msg.content
                else:
                    contents.append({"role": "user", "parts": [{"text": f"[System: {msg.content}]"}]})
            elif msg.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})
            elif msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == "tool":
                # Gemini doesn't have native tool_result — append as user message
                contents.append({"role": "user", "parts": [{"text": f"[Tool result: {msg.content}]"}]})

        return system_prompt, contents

    def chat(self, messages: list[ChatMessage], options: ChatOptions | None = None) -> ChatResponse:
        """Non-streaming chat completion."""
        opts = options or ChatOptions()

        import httpx
        start = time.time()

        system_prompt, contents = self._convert_messages(messages)
        models = self.list_models()
        model_id = models[0].id if models else "gemini-1.5-flash"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": opts.temperature,
                "maxOutputTokens": opts.max_tokens,
                "topP": opts.top_p,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if opts.stop:
            payload["generationConfig"]["stopSequences"] = opts.stop
        if opts.json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        try:
            response = httpx.post(
                f"{self._base_url()}/models/{model_id}:generateContent?key={self._api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("No candidates in response")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

            usage = data.get("usageMetadata", {})
            latency = (time.time() - start) * 1000

            return ChatResponse(
                text=text,
                model_id=model_id,
                provider="google",
                tokens_used=usage.get("totalTokenCount", 0),
                latency_ms=round(latency, 1),
                finish_reason=candidates[0].get("finishReason", "STOP"),
            )
        except Exception as exc:
            logger.error(f"Google chat failed: {exc}")
            raise RuntimeError(f"Google chat failed: {exc}") from exc

    def stream(self, messages: list[ChatMessage], options: ChatOptions | None = None) -> Iterator[str]:
        """Stream chat completion."""
        opts = options or ChatOptions()
        import httpx

        system_prompt, contents = self._convert_messages(messages)
        models = self.list_models()
        model_id = models[0].id if models else "gemini-1.5-flash"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": opts.temperature,
                "maxOutputTokens": opts.max_tokens,
                "topP": opts.top_p,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        try:
            with httpx.stream(
                "POST",
                f"{self._base_url()}/models/{model_id}:streamGenerateContent?key={self._api_key}&alt=sse",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=120.0,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        try:
                            import json as json_mod
                            data = json_mod.loads(line[6:])
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    text = p.get("text", "")
                                    if text:
                                        yield text
                        except (ImportError, Exception):
                            continue
        except Exception as exc:
            logger.error(f"Google stream failed: {exc}")
            raise RuntimeError(f"Google stream failed: {exc}") from exc

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True

    def supports_json(self) -> bool:
        return True
