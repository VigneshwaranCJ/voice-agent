from app.llm.base import LLMResponse, parse_openai_message
from app.sarvam.client import SarvamClient, get_sarvam


class SarvamLLM:
    """Sarvam chat completions with function calling (model: sarvam-105b-conversations by default)."""

    def __init__(self, client: SarvamClient | None = None):
        self.client = client or get_sarvam()

    def _args(self, opts: dict) -> dict:
        return dict(model=opts.get("model"), temperature=opts.get("temperature", 0.3),
                    max_tokens=opts.get("max_tokens", 600), reasoning_effort=opts.get("reasoning_effort"),
                    tool_choice=opts.get("tool_choice", "auto"))

    async def complete(self, messages: list[dict], tools: list[dict] | None = None, **opts) -> LLMResponse:
        res = await self.client.chat(messages, tools=tools, **self._args(opts))
        choice = (res.get("choices") or [{}])[0]
        return parse_openai_message(choice.get("message") or {})


_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = SarvamLLM()
    return _llm


def set_llm(provider) -> None:
    """Swap provider (tests, alternative vendors)."""
    global _llm
    _llm = provider
