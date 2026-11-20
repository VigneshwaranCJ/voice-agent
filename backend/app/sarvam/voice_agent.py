"""Server-side use of Sarvam's official Python SDK (``sarvam-conv-ai-sdk``): a short, headless connection check.

Live calls from browsers use Sarvam's Web SDK, which connects straight to Sarvam (see app/api/sarvam_agents.py):
our host (Catalyst AppSail) can't carry a browser <-> server WebSocket, and the Python SDK connects from wherever it
runs, so relaying browser audio through it would need exactly that. The check below still exercises the real path
end to end (key, org/workspace/app ids, committed agent version, credits) without a microphone:

    start() -> wait_for_connect() -> send_audio(silence) while listening for the greeting -> stop() (always)

It costs a few seconds of Sarvam call time, so it only runs when an admin asks for it.
"""

import asyncio
import base64
import time
from dataclasses import dataclass, field

from pydantic import SecretStr

from app.core.config import get_settings
from app.core.logging import log

SAMPLE_RATE = 16000
CHUNK_MS = 100
_SILENCE = b"\x00\x00" * (SAMPLE_RATE * CHUNK_MS // 1000)  # 16-bit PCM mono silence, one chunk

_running: set[str] = set()  # agent ids with a check in progress (per process): no duplicate sessions


@dataclass
class CheckResult:
    connected: bool = False
    interaction_id: str | None = None
    agent_spoke: bool = False
    agent_audio_ms: int = 0
    first_agent_text: str | None = None
    events: list[str] = field(default_factory=list)
    error: str | None = None
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return {"connected": self.connected, "interaction_id": self.interaction_id, "agent_spoke": self.agent_spoke,
                "agent_audio_ms": self.agent_audio_ms, "first_agent_text": self.first_agent_text,
                "events": self.events[:20], "error": self.error, "seconds": round(self.seconds, 1)}


class CheckBusy(RuntimeError):
    pass


def _explain(e: BaseException) -> str:
    """A short, key-free reason for the admin."""
    name, msg = type(e).__name__, str(e)
    for needle, text in (("Authentication", "Sarvam rejected the Voice Agents API key."),
                         ("Forbidden", "This API key can't use that Sarvam agent."),
                         ("NotFound", "Sarvam agent not found: check the org, workspace and app ids, and that the "
                                      "agent has a committed version."),
                         ("RateLimit", "Sarvam is rate limiting; try again shortly."),
                         ("402", "The Sarvam account is out of credits.")):
        if needle in name or needle in msg:
            return text
    return f"{name}: {msg[:200]}" if msg else name


async def check_connection(agent_key: str, org_id: str, workspace_id: str, app_id: str,
                           agent_variables: dict | None = None, *, connect_timeout: float = 10.0,
                           listen_seconds: float = 6.0) -> CheckResult:
    """Open one headless Sarvam call, wait for the agent's greeting, then hang up. Never raises for Sarvam errors."""
    from sarvam_conv_ai_sdk import (  # imported lazily: the SDK is only needed for this check
        AsyncSamvaadAgent, InteractionConfig, InteractionType, ServerAudioChunkMsg, ServerEventBase,
        ServerTranscriptMsg,
    )
    from sarvam_conv_ai_sdk.messages.types import UserIdentifierType

    s = get_settings()
    if not s.sarvam_agents_api_key:
        return CheckResult(error="Sarvam Voice Agents is not configured (set SARVAM_AGENTS_API_KEY).")
    if agent_key in _running:
        raise CheckBusy("A connection check for this agent is already running.")
    _running.add(agent_key)
    result = CheckResult()
    spoke = asyncio.Event()
    started = time.monotonic()

    async def on_transcript(msg: ServerTranscriptMsg) -> None:
        if str(getattr(msg.role, "value", msg.role)).lower() != "user" and msg.content:
            result.first_agent_text = result.first_agent_text or msg.content[:300]
            spoke.set()

    async def on_audio(msg: ServerAudioChunkMsg) -> None:
        try:
            n = len(base64.b64decode(msg.audio_base64))
        except ValueError:
            n = 0
        rate = msg.sample_rate or SAMPLE_RATE
        result.agent_audio_ms += int(n / 2 / rate * 1000)
        result.agent_spoke = True
        spoke.set()

    async def on_event(event: ServerEventBase) -> None:
        result.events.append(str(getattr(event.type, "value", event.type)))

    agent = None
    try:
        config = InteractionConfig(
            user_identifier_type=UserIdentifierType.CUSTOM, user_identifier="kural-connection-check",
            org_id=org_id, workspace_id=workspace_id, app_id=app_id,
            interaction_type=InteractionType.CALL, sample_rate=SAMPLE_RATE,
            agent_variables=agent_variables or None,
        )
        agent = AsyncSamvaadAgent(
            api_key=SecretStr(s.sarvam_agents_api_key), config=config, base_url=s.sarvam_agents_base_url,
            transcript_callback=on_transcript, audio_callback=on_audio, event_callback=on_event,
        )
        await agent.start()
        result.connected = await agent.wait_for_connect(timeout=connect_timeout)
        result.interaction_id = agent.get_interaction_id()
        if not result.connected:
            result.error = "Couldn't connect to the Sarvam agent in time."
            return result
        # Headless mode: we are the "microphone". Stream silence in real time while waiting for the greeting.
        deadline = time.monotonic() + listen_seconds
        while time.monotonic() < deadline and not spoke.is_set() and agent.is_connected():
            await agent.send_audio(_SILENCE)
            await asyncio.sleep(CHUNK_MS / 1000)
        if spoke.is_set():
            await asyncio.sleep(1.0)  # let a little more of the greeting arrive
        elif agent.is_connected():
            result.error = "Connected, but the agent didn't speak within a few seconds (check its greeting)."
        else:
            result.error = "Sarvam ended the call right after connecting."
        return result
    except Exception as e:  # SDK errors: auth, not found, rate limit, network
        result.error = _explain(e)
        log.warning("sarvam_check_failed", error_type=type(e).__name__)  # never the key or customer data
        return result
    finally:
        if agent is not None:
            try:
                await agent.stop()  # always end the session, whatever happened above
            except Exception:
                log.warning("sarvam_check_stop_failed")
        _running.discard(agent_key)
        result.seconds = time.monotonic() - started
