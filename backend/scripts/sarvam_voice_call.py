"""Talk to a Sarvam Voice Agent from this PC's microphone and speaker (official Python SDK, local test only).

    cd backend
    uv run --with pyaudio python scripts/sarvam_voice_call.py --app-id <agent id>

Reads SARVAM_AGENTS_API_KEY, SARVAM_AGENTS_ORG_ID and SARVAM_AGENTS_WORKSPACE_ID from the environment / .env
(--org-id / --workspace-id override). Prints live transcripts; press Ctrl+C to hang up. The key is never printed.
PyAudio needs PortAudio; on Windows the PyAudio wheel includes it.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import SecretStr  # noqa: E402

from app.core.config import get_settings  # noqa: E402


async def main() -> int:
    from sarvam_conv_ai_sdk import (
        AsyncDefaultAudioInterface, AsyncSamvaadAgent, InteractionConfig, InteractionType, ServerEventBase,
        ServerTranscriptMsg,
    )
    from sarvam_conv_ai_sdk.messages.types import UserIdentifierType

    s = get_settings()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--app-id", default=s.sarvam_agents_app_id)
    p.add_argument("--org-id", default=s.sarvam_agents_org_id)
    p.add_argument("--workspace-id", default=s.sarvam_agents_workspace_id)
    p.add_argument("--language", default=None, help="initial_language_name, e.g. English or Tamil")
    a = p.parse_args()
    if not s.sarvam_agents_api_key:
        print("Set SARVAM_AGENTS_API_KEY in .env first.")
        return 2
    if not (a.app_id and a.org_id and a.workspace_id):
        print("Need --app-id, --org-id and --workspace-id (or the SARVAM_AGENTS_*_ID settings).")
        return 2

    async def on_transcript(msg: ServerTranscriptMsg) -> None:
        who = "You  " if str(getattr(msg.role, "value", msg.role)).lower() == "user" else "Agent"
        print(f"{who}: {msg.content}", flush=True)

    async def on_event(event: ServerEventBase) -> None:
        kind = str(getattr(event.type, "value", event.type))
        if "interrupt" in kind:
            print("  (you interrupted: agent stopped speaking)", flush=True)
        elif "interaction_end" in kind:
            print("  (agent ended the call)", flush=True)

    config = InteractionConfig(
        user_identifier_type=UserIdentifierType.CUSTOM, user_identifier="kural-local-cli",
        org_id=a.org_id, workspace_id=a.workspace_id, app_id=a.app_id,
        interaction_type=InteractionType.CALL, sample_rate=16000,
        **({"initial_language_name": a.language} if a.language else {}),
    )
    agent = AsyncSamvaadAgent(api_key=SecretStr(s.sarvam_agents_api_key), config=config,
                              audio_interface=AsyncDefaultAudioInterface(),
                              transcript_callback=on_transcript, event_callback=on_event,
                              base_url=s.sarvam_agents_base_url)
    try:
        await agent.start()
        if not await agent.wait_for_connect(timeout=10):
            print("Couldn't connect within 10 s (check ids, committed agent version, credits).")
            return 1
        print(f"Connected (interaction {agent.get_interaction_id()}). Speak now; Ctrl+C to hang up.", flush=True)
        await agent.wait_for_disconnect()
        print("Call ended.")
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nHanging up…")
        return 0
    except Exception as e:
        print(f"Call failed: {type(e).__name__}: {str(e)[:200]}")
        return 1
    finally:
        await agent.stop()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(0) from None
