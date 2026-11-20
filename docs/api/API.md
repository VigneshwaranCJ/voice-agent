# API reference

The base path is `/api/v1`. All endpoints except `auth/login`, `public/*` and `/health` need a token:

```
Authorization: Bearer <jwt>
```

A platform admin picks a tenant by adding:

```
X-Tenant-ID: <tenant_id>
```

Interactive docs are at `/docs` (FastAPI OpenAPI).

## Auth
| Method | Path | Notes |
|---|---|---|
| POST | `/auth/login` | `{email, password}` → `{access_token, user}` |
| GET | `/auth/me` | Current user |
| POST | `/auth/change-password` | `{current_password, new_password}` (12+ chars). Own account only. |

## Team (`/users`)
Scope comes from the principal: the selected business's users, or platform admins when none is selected.
| Method | Path | Notes |
|---|---|---|
| GET | `/users` | Anyone in the scope (to pick assignees) |
| POST | `/users` | Admins. `{email, full_name, role, password}`; business roles `tenant_admin` / `tenant_agent` |
| PATCH | `/users/{id}` | Admins. `{full_name?, role?, is_active?}`. Deactivation locks the user out immediately. |
| POST | `/users/{id}/reset-password` | Admins, for someone else. `{new_password}` |

## Email alerts
| Method | Path | Notes |
|---|---|---|
| GET | `/notifications/email` | Admins. `{configured, recipients}` (the business's active admins) |
| POST | `/notifications/email/test` | Admins. Sends a test to yourself; 503 when SMTP isn't configured |

## Tenants & business
| Method | Path | Role |
|---|---|---|
| GET | `/industries` | any |
| GET / POST | `/tenants` | GET: any. POST: platform admin. |
| GET / PUT | `/business-profile` | PUT: tenant admin |

## Agents
| Method | Path | Notes |
|---|---|---|
| GET | `/agents/tools/catalog` | All tools, with their JSON schemas |
| GET / POST | `/agents` | Tools are checked against the agent's industry. |
| GET / PUT | `/agents/{id}` | Changing `industry` without sending `config` resets tools to that industry's defaults. |
| PUT | `/agents/{id}/config` | Creates a new config version |
| GET | `/agents/{id}/config/history` | Earlier config versions |
| POST | `/agents/{id}/chat` | Text test console. Body: `{text, conversation_id?, language?}`. Returns 503 if no Sarvam key is set. |
| POST | `/conversations/{id}/end` | Ends a text-console conversation |

## Knowledge
| Method | Path | Notes |
|---|---|---|
| GET | `/knowledge/documents` | |
| POST | `/knowledge/documents/upload` | Multipart upload: PDF, DOCX, TXT, MD or CSV, up to 16 MB |
| POST | `/knowledge/documents/text` | Add an FAQ or policy as plain text |
| POST | `/knowledge/documents/{id}/reindex` | |
| DELETE | `/knowledge/documents/{id}` | |
| GET | `/knowledge/search?q=` | Test retrieval |

## Business data
| Method | Path | Notes |
|---|---|---|
| GET / POST | `/data/properties` | |
| PUT | `/data/properties/{id}` | |
| GET | `/data/sales-executives` | |
| GET | `/data/departments` | |
| GET / POST | `/data/doctors` | |
| POST | `/data/doctors/{id}/slots/generate` | |

## Integrations
| Method | Path | Notes |
|---|---|---|
| GET / POST | `/integrations/connections` | Credentials are encrypted and never returned |
| POST | `/integrations/connections/{id}/test` | Opens a real connection: PostgreSQL, MySQL or REST |
| DELETE | `/integrations/connections/{id}` | |

## Calls & analytics
| Method | Path | Notes |
|---|---|---|
| GET | `/conversations` | Filters: `status`, `channel`, `language`, `agent_id`, `date_from`, `date_to`, `q` (searches summaries and transcripts); `limit` ≤ 500, `offset` |
| GET | `/conversations/{id}` | Transcript, tool history and escalations |
| GET | `/escalations`, `/leads`, `/appointments` | Leads and escalations include `assigned_to` and `notes` |
| PATCH | `/leads/{id}` | `{status?, assigned_to?, notes?}`; `assigned_to: null` unassigns |
| PATCH | `/escalations/{id}` | `{status?, assigned_to?, notes?}`; assigning an open escalation marks it `assigned` |
| GET | `/analytics/overview` | KPIs; `daily` and `hours` are in the business's timezone; `leads`, `escalations` by status |

## Public widget
| Method | Path | Notes |
|---|---|---|
| POST | `/public/agents/{id}/session` | Returns a 15-min widget token plus the agent's greeting. Only for agents with `public_widget_enabled`. |
| POST | `/public/chat` | `{text, conversation_id?, token}`; the widget token may instead go in `Authorization: Bearer`. Any Content-Type (the widget sends `text/plain` so browsers skip the CORS preflight, which Catalyst AppSail's gateway drops). Any origin, no cookies. |
| POST | `/public/chat/{conversation_id}/end` | `{token}` (or the header). Ends the widget chat (it is then summarised) |
| GET | `/public/sarvam/{agent_id}/{widget_token}/orgs/{org}/workspaces/{ws}/apps/{app}/url` | The widget's **Call** button (Sarvam browser SDK `baseUrl`). Token in the path so no custom header (no preflight). Only for this agent, with the public widget on and an enabled Sarvam link; returns Sarvam's `{url, reference_id}`. |

The session response includes `voice: {org_id, workspace_id, app_id}` when the agent can take Sarvam calls (link enabled and `SARVAM_AGENTS_API_KEY` set), else `null`; the widget shows **Call** only then and loads `/sarvam-voice.js` (built by `vite.voice.config.ts`).

Embed: `<script src="https://YOUR-DASHBOARD/widget.js" data-agent="AGENT_ID" async></script>` (optional `data-color`, `data-title`, `data-position="left"`). Preview: `/widget-demo.html?agent=AGENT_ID`.

## Voice calls: hosted Sarvam Voice Agents
Voice runs only on Sarvam Voice Agents: Sarvam handles speech, the LLM and the voice, and calls our tools over HTTPS,
so no WebSocket passes through our host. (The platform's own STT → LLM → TTS pipeline and `/voice/ws` were removed.)
| Method | Path | Notes |
|---|---|---|
| GET | `/agents/{id}/sarvam` | The agent's link: `org_id`, `workspace_id`, `app_id`, `enabled`, `has_token`, `tool_url`. Never returns the token. |
| PUT | `/agents/{id}/sarvam` | Tenant admin. `{org_id, workspace_id, app_id, enabled}` |
| POST | `/agents/{id}/sarvam/token` | Tenant admin. New tool token, shown once (only its SHA-256 is stored); the old one stops working. |
| POST | `/sarvam/tools/{tool_name}` | Called by Sarvam. `Authorization: Bearer <tool token>`, body = tool arguments as JSON, optional `X-Interaction-Id` (groups a call's tool runs into one conversation). Tenant and agent come from the token. Only the agent's enabled **read-only** tools run; write tools (bookings, leads, transfers) return `ok: false` because the caller's own confirmation can't be checked on this channel yet. 401 for a bad or disabled token. |
| GET | `/agents/{id}/sarvam/call-config` | `{org_id, workspace_id, app_id, agent_variables?}` for a dashboard test call (link values, else `SARVAM_AGENTS_*_ID` defaults; `agent_variables` only with `SARVAM_AGENTS_SEND_CONTEXT=true`). 404 if the agent can't take calls. |
| POST | `/agents/{id}/sarvam/check` | Tenant admin. Server-side connection check with Sarvam's Python SDK (`AsyncSamvaadAgent`, headless): connects, streams silence, waits for the greeting, always `stop()`s. Returns `{connected, interaction_id, agent_spoke, agent_audio_ms, first_agent_text, error, seconds}`. 409 if a check for this agent is already running. Uses a few seconds of Sarvam call time. |
| POST | `/agents/{id}/sarvam/calls` | `{interaction_id}` after a dashboard test call: fetches Sarvam's transcript (Analytics API `GET /analytics/v1/{org}/{ws}/{app}/transcripts/{interaction_id}`, key server-side) and stores it under Calls (channel `sarvam_voice`, same conversation as that call's tool runs). `pending: true` while Sarvam hasn't finished it (nothing stored; retry). Idempotent. |
| POST | `/public/sarvam/calls` | Same for the website widget: `{token, interaction_id}`, any Content-Type. Returns only `{ok, pending}`; the transcript goes to the business's dashboard. |
| POST | `/conversations/{id}/sarvam-transcript` | Re-fetch a Sarvam call's transcript (the call record keeps the interaction id in `call_sessions.external_ref`). |
| GET | `/sarvam/runtime/{agent_id}/orgs/{org}/workspaces/{ws}/apps/{app}/url` | For the Sarvam browser SDK as `baseUrl` (`/api/v1/sarvam/runtime/{agent_id}/`, login in `customHeaders`). Ids must match the link. Adds `X-API-Key: SARVAM_AGENTS_API_KEY` server-side and returns Sarvam's `{url, reference_id}`. 503 if the key isn't set, 402 if Sarvam is out of credits. |
