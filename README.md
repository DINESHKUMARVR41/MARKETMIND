# MARKETMIND — Autonomous Multi-Agent Investment Intelligence

A six-agent investment committee prototype for the Diwali Festiverse Finance track. The application fetches a current quote where a public/keyed provider is reachable, searches recent financial coverage, runs six role-specific reasoning stages, routes directed handoff messages through BAND when credentials are configured, applies a deterministic risk gate, and stores paper-only decisions in SQLite.

> **Important:** This is an educational research simulation, not investment advice. No brokerage API is connected and no real-money order can be placed. Provider data may be delayed, incomplete, rate-limited or unavailable. A synthetic fallback is explicitly labelled and must never be described as a live quote.

## What's upgraded in this version

- Live quote adapter chain: Yahoo Finance chart endpoint (no key) → Alpha Vantage (API key) → visibly labelled synthetic fallback.
- Live news search: GDELT DOC 2.0 first, then Yahoo Finance Search News fallback (no API key), with article titles, domains, timestamps and source links passed into the News Agent, Bull and Bear. Provider failures and successful empty searches are distinguished.
- Six specialized reasoning roles use role-mapped Lyzr agents when configured, then the optional Agent 37 Chair route when enabled, then the Gemini Interactions API when `GEMINI_API_KEY` is configured. Each event records its actual provider and whether live model reasoning was used. Without credentials or when the model fails, deterministic fallback text is clearly identified.
- Lyzr Inference v3 is now actually called for each role that has a matching ID in `LYZR_AGENT_IDS`; a single `LYZR_AGENT_ID` is used for the Chair only. If Lyzr is absent or fails, Gemini is attempted and provider provenance records the attempt chain.
- BAND sends real mention-routed messages using a single orchestrator Agent API key (`BAND_AGENT_API_KEY`) or per-role Agent API keys (`BAND_AGENT_KEYS`). The audit distinguishes delivered BAND messages from local-only handoffs. BAND's remote agents must be registered and in the room; this app does not falsely claim that a message was received or processed by a remote peer.
- Finch skill packs are loaded from `FINCH_SKILLS_DIR` (default `.finch/skills/`) with a backend-local fallback. Finch is not a generic API-key service: use the Finch website, CLI and Remote MCP authorization flow. Local loading alone does not prove marketplace provenance or Remote MCP authorization.
- AdaL report webhook with explicit delivery errors.
- Agent 37 Cloud adapter supports explicit instance provisioning (`POST /api/integrations/agent37/provision`) and hosted Responses API test calls after the instance gateway is configured. Provisioning may incur metered charges and is never automatic.
- SQLite audit history, paper-trade ledger, evidence provenance panel, data caveats and integration health endpoint.

## Data providers

### Quotes

The backend attempts `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}` first. If it fails, it tries Alpha Vantage `GLOBAL_QUOTE` if an API key is configured. If neither returns a usable quote, the app returns a synthetic demo quote with `is_demo: true`, `source: Synthetic demo data`, and provider errors. Yahoo's chart endpoint is a convenience data source, not a guaranteed exchange feed; validate the provider's terms, delay and availability before a public deployment.

### News

The backend queries GDELT DOC 2.0 over a seven-day window first, then tries Yahoo Finance Search News if GDELT fails or returns no articles. Neither requires a key, and neither is exhaustive. A zero-result response is not evidence that no relevant news exists. Each returned article is shown with its URL and metadata. If both providers fail, the News Agent receives an explicit unavailable state rather than fabricated headlines.

## Run on Windows 11

### 1. Backend

Open PowerShell:

```powershell
cd marketmind\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8001
```

API docs: http://localhost:8001/docs

### 2. Frontend

Open a second PowerShell window:

```powershell
cd marketmind\frontend
npm install
npm run dev
```

Open http://localhost:5173

The provided `start-backend.bat` and `start-frontend.bat` launchers are also available.

## Configure live AI reasoning

Create a Gemini Interactions API key in Google AI Studio and put it in `backend/.env`:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Each role uses its configured Lyzr agent first, then the optional Agent 37 Chair route (when explicitly enabled), then Gemini Interactions API as fallback. The report's `model_calls` array and each event's `provider` field show what actually happened. You can also make one explicit test request with `POST /api/integrations/llm/test`; it may consume model quota. A configured key is not proof a call succeeded; inspect the returned provider for each event.

## Configure BAND

The app uses the official BAND Agent API documented at https://docs.band.ai/api/agent-api. For the supported single-agent setup, configure `BAND_AGENT_API_KEY` and `BAND_CHAT_ID`. MARKETMIND authenticates as one BAND identity and posts committee handoffs to that room without mentions or peer mappings. This does not create six BAND agents; Lyzr remains responsible for six specialist roles. The alternative multi-sender mode uses `BAND_AGENT_KEYS` plus actual `BAND_AGENT_PEERS` participant mappings.

Example JSON values (replace placeholders; do not commit real keys):

```env
BAND_AGENT_API_KEY=your-orchestrator-agent-api-key
BAND_CHAT_ID=your-room-id
BAND_AGENT_KEYS={}
BAND_AGENT_PEERS={"analyst":{"id":"participant-id-1","name":"Market Analyst","handle":"marketanalyst"},"news":{"id":"participant-id-2","name":"News Intelligence","handle":"newsintel"},"bull":{"id":"participant-id-3","name":"Bull Advocate","handle":"bulladvocate"},"bear":{"id":"participant-id-4","name":"Bear Challenger","handle":"bearchallenger"},"risk":{"id":"participant-id-5","name":"Risk Guardian","handle":"riskguardian"},"chair":{"id":"participant-id-6","name":"Portfolio Chair","handle":"portfoliochair"}}
```

`POST /api/integrations/band/validate` checks `/me` authentication and access to the configured chat's participants endpoint. `POST /api/integrations/band/test-message` submits one fixed, harmless test post; it is never sent at startup or by tests. The dashboard exposes it as a deliberate action with confirmation. Message submission status is recorded in analysis handoff results, and the test endpoint returns a safe submission state and HTTP status without provider response bodies. An accepted post confirms BAND accepted the message, not that a user read it.

When using role-specific `BAND_AGENT_KEYS` and `BAND_AGENT_PEERS`, `POST /api/integrations/band/validate-all` performs read-only checks for analyst, news, bull, bear, risk, and chair. For each key it calls the existing `/me` and configured room participants endpoints. If `/me` returns an `id`, that value is compared to the role's configured peer `id`; if no ID is returned, the report says identity matching is unverified rather than claiming a match. This operation never sends messages.

`POST /api/integrations/band/connectivity` separately checks DNS, a direct TCP/TLS connection, configured proxy presence/types, and a proxy-aware unauthenticated GET to `/me`. It sends no BAND key and does not post a message; an HTTP 401/403 from that probe indicates the endpoint returned a response, not a credential failure. Role validation reports sanitized exception class chains, descriptions, elapsed milliseconds, and HTTP status when available. It never serializes exception text, authorization headers, or provider response bodies.

## Configure Lyzr

Create and deploy agent(s) in Lyzr Studio. Set:

```env
LYZR_API_KEY=your_lyzr_key
LYZR_AGENT_ID=your_chair_agent_id
```

For separate Lyzr agents by role, set `LYZR_AGENT_IDS` as a JSON object:

```env
LYZR_AGENT_IDS={"analyst":"agent-id-1","news":"agent-id-2","bull":"agent-id-3","bear":"agent-id-4","risk":"agent-id-5","chair":"agent-id-6"}
```

A role uses Lyzr only when its ID exists; otherwise it falls back to Gemini. The API key and agent IDs must come from your own Lyzr workspace.

## Finch skills and Remote MCP

Finch is not a standard REST API key integration. Its official model separates the website, Remote MCP and Finch CLI. The local Analyst, News and Risk roles load skill files from `FINCH_SKILLS_DIR` (default `.finch/skills/`, which is Finch CLI's project skill directory). To use marketplace-origin skills, download them from your Finch account and replace/add the relevant `SKILL.md` packages in that directory. The project reports local skill loading separately from CLI installation and Remote MCP endpoint configuration.

Official Remote MCP endpoint: `https://www.finchtech.ai/mcp`. Follow Finch's current CLI/MCP OAuth instructions in https://www.finchtech.ai/en/story/cli-mcp. Do not create or paste a generic `FINCH_API_KEY`; this project does not use one. The backend's `/api/integrations/finch/doctor` endpoint runs `finch mcp doctor` if the Finch CLI is installed on the same machine as the backend. The command's output is suppressed to avoid disclosing local configuration. A successful local doctor exit is not evidence that MARKETMIND has called a remote MCP tool; it currently has no such client.

## AdaL inbound webhook

Create an Inbound Server in Adal Cloud and copy its exact Public Ingest URL to `ADAL_WEBHOOK_URL`. A Server only receives requests. To forward them, create a Channel, add an Endpoint that points to a publicly reachable MarketMind `/api/webhooks/adal` receiver (or use Adal CLI to forward to a local backend), and connect the Server to the Channel with a Router. See https://adal.cloud/en/docs/inbound/servers and https://adal.cloud/en/docs/quickstart.

`ADAL_WEBHOOK_TOKEN` is optional and is a shared secret YOU generate; it is not the Adal CLI token. If used, configure the same secret as an Endpoint forwarding header `X-MarketMind-Webhook-Token`. Use **Send to AdaL** after a completed analysis. A 2xx response confirms Adal accepted the inbound request; inspect Adal Delivery history to confirm it reached the destination. The app also exposes `GET /api/adal/events` for deliveries received by its webhook endpoint.

## Agent 37 Cloud

Agent 37 is a managed agent runtime, not simply a place to host this FastAPI backend. The adapter supports the documented Cloud API: create an instance with `POST https://api.agent37.com/v1/instances`, then call the instance's OpenAI-compatible `/v1/responses` endpoint. See https://www.agent37.com/cloud.

Set `AGENT37_API_KEY` in `backend/.env`. Provisioning is an explicit, potentially billable action: call `POST /api/integrations/agent37/provision` once you are ready. Copy the returned instance ID and URL into `AGENT37_INSTANCE_ID` and `AGENT37_INSTANCE_URL`. Configure the Hermes instance's own `API_SERVER_KEY` inside the instance and put that value in `AGENT37_INSTANCE_API_KEY`. This is a separate key from the Agent 37 workspace provisioning key. Then use `POST /api/integrations/agent37/test` to verify a hosted response. To route the Portfolio Chair through Agent 37 before Gemini fallback, set `AGENT37_USE_FOR_CHAIR=true`. No instance is created automatically by an analysis run.

## Integration activation checklist

These are the exact settings consumed by the active adapters. Put secrets only in `backend/.env` or the backend host's secret manager. A value being present is configuration only; it is not proof of authentication or delivery.

### BAND

1. In BAND, register the sender agent(s), create a shared room, and add each recipient participant to that room. Copy the room ID into `BAND_CHAT_ID`.
2. Choose one authentication mode:
   - Single sender identity: set `BAND_AGENT_API_KEY` to that identity's Agent API key. This authenticates all outgoing handoffs as the same BAND identity.
   - Distinct sender identities: set `BAND_AGENT_KEYS` to a JSON object with `analyst`, `news`, `bull`, `bear`, `risk`, and `chair` keys, each mapped to that role's Agent API key. Example shape: `{"analyst":"...","news":"...","bull":"...","bear":"...","risk":"...","chair":"..."}`.
3. Set `BAND_AGENT_PEERS` to a JSON object with all six role names. Each value needs the actual `id`, `name`, and `handle` of that BAND room participant. Example shape: `{"analyst":{"id":"...","name":"Market Analyst","handle":"..."},"news":{"id":"...","name":"News Intelligence","handle":"..."},"bull":{"id":"...","name":"Bull Advocate","handle":"..."},"bear":{"id":"...","name":"Bear Challenger","handle":"..."},"risk":{"id":"...","name":"Risk Guardian","handle":"..."},"chair":{"id":"...","name":"Portfolio Chair","handle":"..."}}`.
4. `BAND_VALIDATE_ROLE` optionally selects the sender role for the explicit identity check; default is `analyst`.

The adapter authenticates with `X-API-Key` and uses the Agent API paths `/me`, `/chats/{chat_id}/participants`, and `/chats/{chat_id}/messages`. `POST /api/integrations/band/validate` checks identity and room access; it does not send a message. A real handoff is only recorded as successful after BAND accepts the message POST. Neither response proves a recipient processed the message. Missing-key state from the diagnostics endpoint names the variables to fill.

### Finch

`FINCH_SKILLS_DIR` is the local folder for skill packs; the current checkout already has local skills. This is separate from Finch CLI installation and account authorization. There is no Finch API key variable in this integration. Install the Finch CLI and complete Finch's own Remote MCP/OAuth setup using its current [CLI/MCP instructions](https://www.finchtech.ai/en/story/cli-mcp). `FINCH_MCP_URL` is only a configured URL value consumed by status reporting; setting it does **not** connect MCP. The code can run `finch mcp doctor` locally, but MARKETMIND currently has no Remote MCP client/tool invocation, so remote skills cannot be activated by environment configuration alone. Local skill availability, CLI presence, remote authorization, and a remote tool operation must be treated as separate states.

### AdaL

1. Set `ADAL_WEBHOOK_URL` to the exact Public Ingest URL of the AdaL Inbound Server.
2. For forwarding inbound AdaL deliveries to MARKETMIND, configure an AdaL Channel, Endpoint, and Router. The Endpoint destination must be the public `POST /api/webhooks/adal` URL.
3. Generate your own high-entropy shared secret for `ADAL_WEBHOOK_TOKEN`; it is **not** an AdaL credential or CLI token. Configure the same secret as the Endpoint's `ADAL_WEBHOOK_HEADER` header, whose default name here is `X-MarketMind-Webhook-Token`. `ADAL_WEBHOOK_HEADER` can change the header name. The receiver accepts unauthenticated webhook requests if the token is left blank, so set it before exposing the receiver.

The outgoing notifier sends a completed report to `ADAL_WEBHOOK_URL`, with `X-Event-Id: marketmind-run-{run_id}` and the configured shared-secret header when set. An HTTP success means the ingest URL accepted the request; it does not verify downstream delivery. Incoming duplicate protection uses `event_id`, `id`, or `X-Event-Id`, and falls back to a hash of the JSON payload. `GET /api/adal/events` shows accepted inbound event history. No authenticated external delivery has been verified as part of this audit.

### Agent 37

1. `AGENT37_API_KEY` is the Agent 37 workspace key. The provisioning adapter sends it as `Authorization: Bearer ...` to `POST https://api.agent37.com/v1/instances` with JSON `{"template":"..."}`. `AGENT37_TEMPLATE` selects the template (default `agent37-hermes`). Provisioning can incur charges; it is deliberately not automatic and was not run for this audit.
2. After you independently provision/configure an instance, set `AGENT37_INSTANCE_ID` and `AGENT37_INSTANCE_URL` from the instance's returned ID and URL.
3. Configure the instance's Hermes gateway `API_SERVER_KEY` yourself, then set that value as `AGENT37_INSTANCE_API_KEY`. Hosted inference sends this separate key as Bearer auth to `{AGENT37_INSTANCE_URL}/v1/responses`.
4. `AGENT37_MODEL` selects the hosted model (default `hermes`). `AGENT37_USE_FOR_CHAIR` is optional and defaults to `false`; it only routes the Chair through the host after hosted inference is configured.

The workspace key alone is not enough for hosted inference, and the three inference settings being present still do not prove successful authentication. `POST /api/integrations/agent37/test` is the explicit actual inference check; it was not called during this audit.

## Integration diagnostic states

`GET /api/integrations/diagnostics` is a local configuration inspection and makes no network or CLI calls. It reports missing settings separately from `configured_unverified` and explicitly marks authentication/operations as not checked. Explicit checks and real operations classify their responses as `authentication_rejected`, `network_failure`, `authentication_succeeded`, or `operation_succeeded` where supported. BAND identity success is not message delivery; AdaL ingest acceptance is not downstream delivery; Finch CLI doctor is not a remote MCP tool operation. No diagnostics endpoint should treat configured credentials as proof of success.

## API

- `GET /api/health` — configured provider status (not a guarantee of successful live requests)
- `GET /api/agents` — six agent roles
- `GET /api/quote/{symbol}` — quote provider chain and explicit synthetic fallback
- `GET /api/history-prices/{symbol}?range_=1mo&interval=1d` — chart history from Yahoo chart endpoint
- `GET /api/news/{symbol}?company=Company%20Name` — GDELT + Yahoo Finance news search chain
- `POST /api/analyze` — six-stage committee run and audit provenance
- `POST /api/paper-trade/{run_id}` — paper BUY only when deterministic risk gate approves
- `GET /api/history` and `GET /api/history/{run_id}` — saved analysis reports
- `GET /api/trades` — paper execution ledger
- `POST /api/adal/notify/{run_id}` — send report to configured AdaL ingest URL
- `POST /api/webhooks/adal` — receive forwarded AdaL deliveries (optional shared-header validation)
- `GET /api/adal/events` — inspect received AdaL deliveries
- `GET /api/integrations` — integration readiness and credential-presence metadata (never secrets)
- `GET /api/integrations/diagnostics` — local-only configuration diagnostics; makes no network or CLI calls
- `POST /api/integrations/band/validate` — validate configured BAND identity and room access
- `POST /api/integrations/band/validate-all` — validate all six role identities, configured peer ID matches where exposed, and room access; read-only
- `POST /api/integrations/band/connectivity` — credential-free DNS/TCP/TLS/proxy/HTTP connectivity diagnostic; read-only
- `POST /api/integrations/band/test-message` — explicitly submit a fixed test message to the configured BAND chat
- `POST /api/integrations/llm/test` — make one explicit live Lyzr/Gemini inference test for a selected role
- `POST /api/integrations/finch/doctor` — run local Finch MCP diagnostics
- `POST /api/integrations/agent37/provision` — explicitly provision a billable Agent 37 instance
- `POST /api/integrations/agent37/test` — send a prompt to configured Agent 37 instance

## Tests

From `backend`:

```powershell
python -m compileall -q app
python smoke_test.py
```

The smoke test checks the API, six agent events, six handoffs, paper-only execution and provider provenance. External provider connectivity depends on your network and credentials; this project environment cannot verify your personal keys or sponsor workspaces.

## Suggested two-minute demo

1. Show `/api/health` to establish which providers are configured.
2. Analyze a symbol and show the quote source, timestamp and live/demo label.
3. Show the GDELT headlines and source links used by News Intelligence.
4. Open the transcript and show provider provenance for all six agent outputs.
5. Show Bull vs Bear challenge and directed BAND handoffs; open the BAND room to prove message delivery.
6. Show the deterministic Risk Guardian gate and the Chair's final decision.
7. Record a paper trade only if BUY and risk-approved; replay the audit report.

## Sponsor integration truth table

| Sponsor | Code in repo | What still needs your account action |
|---|---|---|
| BAND | Agent API send bridge | Register agents, create room, add participants, configure keys/IDs; remote WebSocket workers are separate |
| Lyzr | Live Inference v3 adapter with Gemini fallback | Create/deploy Lyzr agents and add API key + IDs; run a live test |
| Finch | Finch-compatible `.finch/skills` loader + CLI doctor | Download actual marketplace skills and authorize Remote MCP/CLI; local packs alone are not marketplace proof |
| AdaL | Inbound webhook sender + receiver | Create Server, Channel, Endpoint and Router; optional shared secret is user-generated |
| Agent37 | Cloud instance provision + Responses API adapter | Provision instance, configure its gateway key and test hosted inference; provisioning may incur charges |

## Stack

React, Vite, Recharts, Lucide React, FastAPI, Pydantic, SQLite, Yahoo Finance chart endpoint, Alpha Vantage, GDELT DOC 2.0, Gemini Interactions API, optional Lyzr inference and BAND Agent API.

## Production deployment

Build the frontend with `cd frontend; npm ci; npm run build` and serve `frontend/dist` from a static host. Set the build-time `VITE_API_URL` to the public HTTPS URL of the backend; this value is public and must never contain credentials. Set the backend `FRONTEND_ORIGIN` to the exact static-site origin and configure the remaining provider variables only in the backend's secret environment. Run the API with `uvicorn app.main:app --host 0.0.0.0 --port $PORT` from `backend` (or deploy with the included `Procfile`/`Dockerfile`).

Mount persistent storage for SQLite and set `DATABASE_PATH` to a writable absolute path on that volume. Backups should include this database file. A container's ephemeral filesystem is not persistent. Use HTTPS for the app and webhook receiver, restrict CORS to the deployed frontend origin, and protect webhook ingress with a generated `ADAL_WEBHOOK_TOKEN`. Do not expose `/docs` publicly unless intended. External provider calls are made by the backend; missing credentials leave those integrations unavailable and do not block local demo reasoning or paper-only records.

The `Integrations` dashboard reports configured state and exposes explicit connection checks. A configured credential is not considered live until its check or a real analysis call succeeds. Agent 37 provisioning is deliberately a separate API action and may incur charges.
