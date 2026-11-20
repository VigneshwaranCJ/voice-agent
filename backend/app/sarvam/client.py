"""Sarvam AI REST client (chat completions for text chat and the website widget). Docs: https://docs.sarvam.ai

Voice calls run on hosted Sarvam Voice Agents (see app/api/sarvam_agents.py), not through this client.
"""

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import log


class SarvamError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status, self.code = status, code


class SarvamNotConfigured(SarvamError):
    def __init__(self) -> None:
        super().__init__("SARVAM_API_KEY is not configured", code="not_configured")


_RETRY_STATUS = {429, 500, 502, 503}


class SarvamClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 30.0):
        s = get_settings()
        self.api_key = api_key or s.sarvam_api_key
        self.base_url = (base_url or s.sarvam_base_url).rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise SarvamNotConfigured()
        return {"api-subscription-key": self.api_key, "Authorization": f"Bearer {self.api_key}"}

    async def _request(self, method: str, path: str, *, retries: int = 2, **kw) -> dict:
        headers = self._headers()
        delay = 0.5
        for attempt in range(retries + 1):
            try:
                r = await self._client.request(method, f"{self.base_url}{path}", headers=headers, **kw)
            except httpx.TransportError as e:
                if attempt < retries:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise SarvamError(f"Network error contacting Sarvam: {e}") from e
            if r.status_code in _RETRY_STATUS and attempt < retries:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if r.status_code >= 400:
                try:
                    err = r.json().get("error", {})
                except ValueError:
                    err = {}
                log.warning("sarvam_error", path=path, status=r.status_code, body=r.text[:500])
                raise SarvamError(err.get("message") or r.text[:300], r.status_code, err.get("code"))
            return r.json()
        raise SarvamError("unreachable")

    async def chat(self, messages: list[dict], *, tools: list[dict] | None = None, model: str | None = None,
                   temperature: float = 0.3, max_tokens: int = 600, reasoning_effort: str | None = None,
                   tool_choice: str = "auto") -> dict:
        s = get_settings()
        body: dict[str, Any] = {"model": model or s.sarvam_llm_model, "messages": messages,
                                "temperature": temperature, "max_tokens": max_tokens}
        if reasoning_effort or s.sarvam_llm_reasoning_effort:
            body["reasoning_effort"] = reasoning_effort or s.sarvam_llm_reasoning_effort
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        return await self._request("POST", "/v1/chat/completions", json=body, timeout=s.llm_timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()


_client: SarvamClient | None = None


def get_sarvam() -> SarvamClient:
    global _client
    if _client is None:
        _client = SarvamClient()
    return _client
