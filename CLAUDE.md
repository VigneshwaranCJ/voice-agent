# CLAUDE.md — project conventions

Multi-tenant AI customer-care voice platform on Sarvam AI. FastAPI backend (`backend/`) and React/Vite dashboard (`frontend/`). See `docs/architecture/ARCHITECTURE.md`.

## Commands
- Backend dev: `uv run --directory backend uvicorn app.main:app --port 8000 --reload`
- Frontend dev: `npm --prefix frontend run dev` (port 5173, proxies `/api` and WS to :8000)
- Tests: `cd backend && uv run pytest -q -p no:cacheprovider -W ignore`. They use a scripted LLM and need no key.
- Frontend type-check: `cd frontend && npx tsc --noEmit`

## Hard rules
- **No secrets in code.** Keys and credentials go only in `.env`, which is git-ignored. Never print `SARVAM_API_KEY`.
- **No fake integrations.** If something isn't wired up, return a clear error or "not configured". Don't simulate success.
- **Tenant isolation everywhere.** Every query filters by `tenant_id` from the principal or `ToolContext`, never from request bodies or LLM arguments. Add an isolation test for every new data path.
- **The engine stays industry-agnostic.** Industry logic lives in `app/industries/<name>/` (module, tools, models). The engine only sees the `IndustryModule` interface.
- **Tools** are registered with `@tool(...)` and Pydantic params. Writes that change bookings use `requires_confirmation=True`, which runs only after the *caller's* explicit yes.
- **No PII without verification.** A phone number identifies; it doesn't verify. Never return stored customer data to the model on a phone match alone.
- **Voice runs only on hosted Sarvam Voice Agents.** Their tool calls authenticate with a per-agent tool token (hashed); tenant and agent come from it. Never put a login JWT in a URL.
- Emergency and other guard regexes must be word-bounded for Latin script.

## Gotchas
- **SQLAlchemy async:** a rollback expires ORM objects, and a later lazy load raises `MissingGreenlet`. Keep plain ids (`CallRef`) or expunged objects across commits and rollbacks.
- **SQLite stores naive UTC.** Use `app.core.timeutil.as_utc` before comparing datetimes.
- **Sarvam chat:** if tool messages are present, `tools` must be sent too. To force a final answer, use `tool_choice="none"`, not `tools=None`. HTTP 402 means out of quota. Don't retry or reconnect on 401, 402 or 403 (or WS close code 1003).
- **Windows:** set `PYTHONIOENCODING=utf-8` when printing Tamil. When editing Python that contains regex backslashes, avoid shell heredocs that interpret `\b` or `\n`.
- **The retrieval cache** is per process and invalidated by document `updated_at`. Anything that changes chunks must bump it, as `index_document` does.

## Docs
- `docs/ROADMAP.md`: status.
- `docs/REVIEW_FIXES.md`: review fixes log.
- `docs/security/SECURITY.md`, `docs/setup/SETUP.md`, `docs/api/API.md`, `docs/testing/TESTING.md`.
