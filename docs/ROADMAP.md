# Roadmap

Legend: ✅ done · 🟡 partial · ⬜ pending

## Phase 1 — Foundation ✅
- ✅ Project structure (backend / frontend / infrastructure / docs)
- ✅ FastAPI app, Pydantic settings, structured logging, rate limiting, CORS
- ✅ SQLAlchemy models for all core tables (tenant_id everywhere) + Alembic initial migration
- ✅ JWT auth, RBAC (`platform_admin`, `tenant_admin`, `tenant_agent`), audit log
- ✅ Multi-tenancy: tenant-scoped API + tools + retrieval, `X-Tenant-ID` for platform admins, isolation tests
- ✅ Fernet-encrypted integration credentials; PostgreSQL / MySQL / REST connection tests
- ✅ React + TS + Vite + Tailwind dashboard
- 🟡 PostgreSQL + Redis via Docker Compose — config written, **not yet run** (Docker Desktop was not running). Local dev verified on SQLite + in-memory state.

## Voice on hosted Sarvam Voice Agents 🟡 (2026-11-20)
- ✅ Own STT → LLM → TTS voice pipeline removed (WebSocket, streaming STT/TTS, voice profiles, Voice page, avatars). Migration `0003` drops `voice_profiles` and `agents.voice_profile_id`.
- ✅ Per-agent Sarvam link + hashed tool token; tool webhook `/sarvam/tools/{tool}` runs the agent's read-only tools (tenant from the token); session route for the Sarvam browser SDK; Agents page panel; isolation tests.
- ⬜ Verify with a real Sarvam agent (tool request format isn't in Sarvam's public docs).
- ⬜ Bookings on the Sarvam channel (needs a way to confirm the caller's own "yes").
- ✅ Browser calls via Sarvam's Web SDK (dashboard **Test call**, website widget **Call**), barge-in, dropped-call and mic-denied states; transcripts saved under Calls.
- ✅ Python SDK (`AsyncSamvaadAgent`) connection check and local mic test script; optional business `agent_variables`. Architecture and AppSail assessment: `docs/deploy/SARVAM_VOICE.md`.
- ⬜ First real call with credits, a committed Sarvam agent and `SARVAM_AGENTS_API_KEY`.

## Phase 2 — Voice engine (removed 2026-11-20; replaced by Sarvam Voice Agents above)
- ✅ Sarvam realtime STT WebSocket (`saaras:v4`, VAD endpointing, auto language detection)
- ✅ Sarvam streaming TTS WebSocket (`bulbul:v4-flash`, per-language persona, pace, temperature)
- ✅ Sarvam chat completions with tool calling (`sarvam-105b-conversations`)
- ✅ Browser voice console: AudioWorklet 16 kHz PCM capture, MediaSource MP3 playback
- ✅ Barge-in (VAD speech start cancels TTS + client playback), silence prompts + timeout, STT reconnect, TTS failure fallback to text
- ✅ Live-tested 2026-11-17: REST + streaming STT (EN/TA, language detected), REST + streaming TTS (~0.7 s to first audio), chat tool calling, multi-turn site-visit and doctor bookings
- ⬜ Live microphone call in the browser console (needs a human caller)
- ⬜ Phone channel (Twilio/Exotel media streams → same `VoiceSession`, 8 kHz μ-law)
- ✅ LLM token streaming → sentence-level TTS, TTS socket opened while the LLM thinks (measured: first audio ~0.85 s vs ~1.27 s before). `LLM_STREAMING=false` turns it off

## Phase 3 — Intelligence 🟡
- ✅ Context manager (business / customer / conversation), dynamic system prompts, grounding rules
- ✅ Tool registry: validation, timeouts, confirmation gate, audit, structured errors
- ✅ Guardrails: emergency (EN/TA/Tanglish/HI), human-request, repeated-failure escalation
- ✅ Human handoff records with context summary
- ✅ Post-call analyst agent (2026-11-27): sentiment, outcome, summary, key quotes and follow-ups for every ended text chat and Sarvam call. Validated tool output with self-correction, fact checks against tool runs and escalations, and an automatic follow-up when a person should call back (`ANALYSIS_AUTO_FOLLOW_UP`). Shown in Calls (column, filter, analysis card) and on the dashboard. ⬜ Bulk analysis of calls that ended before this shipped
- 🟡 RAG: BM25 keyword retrieval (tenant + agent scoped). ⬜ pgvector embeddings + hybrid search (needs embedding provider choice)
- ⬜ Caller verification (OTP) before sharing sensitive records
- ⬜ Admin-defined tools over external DB/REST connections

## Phase 4 — Industry modules 🟡
- ✅ Real estate: search, details, availability, pricing, lead capture, site visit booking, sales executive assignment
- ✅ Healthcare: doctor search, schedules, availability, book / cancel / reschedule, departments, staff transfer, emergency guard
- ✅ Custom: knowledge + leads + handoff with admin instructions
- ⬜ Hospitality (rooms, reservations, modifications, cancellation policy) — currently falls back to custom
- ⬜ Education, banking, e-commerce

## Phase 5 — Dashboard 🟡
- ✅ Dashboard KPIs, business onboarding, business profile, agent config (versioned), voice/languages/tools, knowledge upload/reindex/search test, integrations, calls list + transcript + tool history + escalations, business data views
- ✅ Team management (add people, roles, deactivate with immediate lock-out, admin password reset), change password
- ✅ Follow-ups: lead and escalation workflow (status, assignee, notes, filters, search, CSV export)
- ✅ Agent test chat over HTTP (no microphone or WebSockets needed), config version history with restore, opening-hours editor
- ✅ Calls: filters (status, channel, dates), transcript search, CSV export, load more
- ✅ Analytics: busiest hours and days in the business timezone, lead pipeline, outcomes
- ✅ Website chat widget (`widget.js`, HTTP only, Shadow DOM) with embed snippet and preview page
- ✅ Email alerts to business admins on new leads and handoffs (any SMTP provider; off until configured)
- ⬜ CRUD forms for properties/doctors in UI (API exists), CSAT capture, recordings (consent-aware)

## Phase 6 — Production ⬜
- ✅ Backend test suite (43 tests), Dockerfiles, compose, nginx WS proxy
- ✅ Codebase review: 10 findings fixed (emergency regex, PII on phone match, WS tickets, rollback safety, rate limiter, agent update checks, retrieval cache). See [REVIEW_FIXES.md](REVIEW_FIXES.md)
- ⬜ Run on PostgreSQL in CI, frontend tests, load test of concurrent voice sessions
- ⬜ Redis-backed rate limiting, secrets manager, data-retention job, monitoring/metrics (Prometheus/OTel), deployment guide
