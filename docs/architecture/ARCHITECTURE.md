# Architecture — Multi-Industry AI Customer Care Voice Platform

Status: Phase 1 (foundation) implemented. **Voice changed (2026-11-20):** the platform's own STT → LLM → TTS pipeline
(browser WebSocket, `VoiceSession`, Sarvam streaming STT/TTS, voice profiles, the Voice page and avatars) was removed.
Voice calls now run only on hosted **Sarvam Voice Agents**, which call our tools over HTTPS
(`app/api/sarvam_agents.py`, see `docs/api/API.md`). The engine (guardrails → context → LLM ⇄ tools) remains for text
chat and the website widget. Sections below that describe the voice WebSocket and streaming are historical.
See `docs/ROADMAP.md`.

## Decisions (confirmed for MVP)

| Decision | Choice | Why |
|---|---|---|
| Voice infrastructure | Custom platform on Sarvam REST/WebSocket APIs (no managed Voice Agents) | Full control over tenant data, tools, workflows |
| Real-time transport | Browser ⇄ FastAPI WebSocket ⇄ Sarvam streaming WebSockets | No extra media server needed for the web channel. LiveKit/Twilio adapters plug into the same `VoiceSession` later |
| Channels | Website voice first; phone (Twilio/Exotel media streams) is Phase 2b | Phone reuses the same session bridge with an 8 kHz μ-law transport |
| Languages | Tamil (`ta-IN`) + English (`en-IN`) default; any Sarvam language configurable per agent | STT runs with `language_code=auto`; reply language follows the caller |
| LLM | Sarvam `sarvam-105b-conversations` (chat completions, function calling) behind an `LLMProvider` interface | Swappable provider |
| DB | PostgreSQL (prod, via Docker) — SQLite accepted for local dev/tests | Same SQLAlchemy models, portable types |
| Retrieval | Keyword (BM25) retrieval over tenant-scoped chunks now; pgvector embeddings in Phase 3 | Needs an embedding-provider decision |
| Session state | Redis when `REDIS_URL` set, in-process store otherwise | |

## Sarvam APIs used (verified against docs.sarvam.ai on 2026-11-17)

| Purpose | Endpoint | Model |
|---|---|---|
| Streaming STT | `wss://api.sarvam.ai/speech-to-text-realtime/ws` (VAD endpointing, partial + final transcripts, language detection) | `saaras:v4` |
| Batch/short STT (text fallback, uploads) | `POST /speech-to-text` | `saaras:v4` |
| Streaming TTS | `wss://api.sarvam.ai/text-to-speech/ws` (config → text → flush, MP3 chunks) | `bulbul:v4-flash` (the API id for "Bulbul v4") |
| REST TTS (previews) | `POST /text-to-speech` | `bulbul:v4-flash` |
| LLM | `POST /v1/chat/completions` with `tools` | `sarvam-105b-conversations` |

Auth header: `api-subscription-key`. Default voices: `aparna_en_companion` (en-IN, Sarvam's top pick for empathetic customer care) and `gokul_ta_narration` (ta-IN — Sarvam publishes no Tamil "customer" persona; audition and change per business). Bulbul v4 voices are persona ids `<name>_<lang>_<style>`, configured per voice profile and per language.

## Component view

```
Browser (React)  ──WS /api/v1/voice/ws──▶  VoiceSession (app/voice/session.py)
  mic 16kHz PCM16 ─────────────────────▶     ├─ SarvamRealtimeSTT  ──▶ Sarvam STT WS
  MP3 chunks (MediaSource) ◀────────────     ├─ AgentEngine (app/orchestration/engine.py)
  events: transcript / interrupt / state     │     ├─ ContextManager (business + customer + conversation)
                                             │     ├─ LLMProvider (Sarvam chat, tool calling)
                                             │     ├─ ToolRegistry (tenant-scoped, validated, timed out, audited)
                                             │     └─ Guardrails (emergency, human request, distress)
                                             └─ SarvamStreamingTTS ──▶ Sarvam TTS WS
```

### Shared engine vs. industry modules

The engine has **no industry logic**. Each industry is an `IndustryModule` (`app/industries/<name>/`) that contributes:
- its own tables (`properties`, `sales_executives`, `departments`, `doctors`, `doctor_slots`, …), all with `tenant_id`;
- tools (`search_properties`, `book_appointment`, …) registered into the `ToolRegistry`;
- default instructions and guardrail hooks (e.g. healthcare emergency rules).

An agent selects which tools are enabled (`agent_configurations.enabled_tools`). A *custom* industry uses only common tools (knowledge search, lead capture, human handoff) plus admin-written instructions; external REST/DB tools are Phase 3/4.

### Context management

`ContextManager.build()` assembles only what the current turn needs:
1. **Business context** — business profile (hours, locations, contact), active agent config, top-k knowledge chunks for the latest user utterance.
2. **Customer context** — only after identification (`identify_customer` tool by phone match). A phone number is **not** verification, so no stored PII (name, appointments, enquiries) is returned to the model or put in the prompt — only "unverified caller" plus record counts. Sensitive actions re-check the phone against the booking itself. OTP verification is on the roadmap.
3. **Conversation context** — Redis/in-memory session state: message history (trimmed), collected slots, detected language (from STT, or from script for typed text).

Structured facts (availability, pricing, schedules) are *never* put in the prompt wholesale; the LLM must call tools. The system prompt forbids inventing them.

### Post-call analyst agent

`app/analysis/agent.py` runs after a conversation ends: from `end_conversation` (text chat, widget) and from `save_transcript` (Sarvam calls). It can also be re-run with `POST /conversations/{id}/analysis`.

1. **Evidence.** It loads the transcript, tool runs, escalations and call record, all filtered by the conversation's `tenant_id`.
2. **Reason.** The LLM must hand in its findings by calling `submit_analysis`, a tool whose parameters are the `AnalysisIn` Pydantic schema.
3. **Self-correct.** A missing or invalid submission goes back to the model with the validation errors. It gets up to 3 attempts.
4. **Verify.** Recorded facts override the model. Quotes not found in the caller's words are dropped. "booked" needs a successful booking tool run, and "lead_captured" a successful write tool. Escalated conversations stay escalated. Each correction is listed in `checks`.
5. **Act.** It saves one `conversation_analyses` row per conversation and replaces the conversation's summary. It sets `resolved` if nothing else did. If a person should follow up and nothing is open, it opens a `follow_up` escalation, once per conversation.

It never raises for model trouble. The row's `status` (`done`, `failed`, `not_configured`, `skipped`) says what happened. It is industry-agnostic: it reads tool registry flags, never industry tables.

### Tenant isolation

- Every tenant-owned row carries `tenant_id`; all repository/tool queries filter by it (`ToolContext.tenant_id` is fixed by the session, never by LLM arguments).
- JWT carries `tenant_id` and `role`. Roles: `platform_admin` (cross-tenant, must pass `X-Tenant-ID`), `tenant_admin`, `tenant_agent` (read-only operations).
- Knowledge retrieval is tenant + agent scoped.
- Tests in `backend/tests/test_tenant_isolation.py` assert cross-tenant access is refused.

### Voice session lifecycle

1. Browser opens WS with `agent_id` (public demo token or user JWT).
2. Server resolves tenant + agent, creates `call_session` + `conversation`, sends greeting (TTS).
3. Mic audio is forwarded to Sarvam STT; `vad.speech_start` while the agent is speaking ⇒ **barge-in**: TTS task cancelled, `interrupt` event sent so the browser stops playback.
4. `transcript.final` ⇒ AgentEngine turn (guardrails → context → LLM ⇄ tools loop, max 4 rounds, 20 s budget) ⇒ reply text ⇒ streaming TTS in the detected language.
5. Escalation (human request, emergency, distress, policy) ⇒ `escalation_records` row with summary, `handoff` event to the client.
6. On close: transcript persisted, summary generated, `call_events` + `analytics_events` written.

Failure handling: STT/TTS disconnects are reported to the client and retried once; tool failures/timeouts are returned to the LLM as structured errors so it apologises instead of inventing; LLM failure ⇒ polite fallback line + offer of human handoff.

### Security

- Passwords: PBKDF2-SHA256 (600k iterations). JWT HS256 with `JWT_SECRET`.
- Credentials for business DB connections are Fernet-encrypted (`ENCRYPTION_KEY`) and never returned by the API.
- Per-IP rate limiting middleware; request validation via Pydantic; audit log for admin writes and tool executions.
- Bookings/cancellations require explicit caller confirmation (`requires_confirmation` tools).
- Call recording is off by default and requires per-agent consent setting (Phase 5).

## Data model

Core tables: `tenants, users, roles, business_profiles, agents, agent_configurations, voice_profiles, supported_languages, database_connections, knowledge_documents, knowledge_chunks, customers, conversations, conversation_messages, conversation_analyses, call_sessions, call_events, tool_definitions, tool_executions, appointments, leads, escalation_records, analytics_events, audit_logs`.

Industry tables: `properties, sales_executives` (real estate), `departments, doctors, doctor_slots` (healthcare). Site visits and doctor bookings both go to the shared `appointments` table.

Migrations: Alembic in `backend/migrations`.
