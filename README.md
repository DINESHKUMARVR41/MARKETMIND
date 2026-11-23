# MARKETMIND — Autonomous Multi-Agent Investment Intelligence

A six-agent investment committee prototype for the Diwali Festiverse Finance track. The application fetches a current quote where a public/keyed provider is reachable, searches recent financial coverage, runs six role-specific reasoning stages, routes directed handoff messages through BAND when credentials are configured, applies a deterministic risk gate, and stores paper-only decisions in SQLite.

> **Important:** This is an educational research simulation, not investment advice. No brokerage API is connected and no real-money order can be placed. Provider data may be delayed, incomplete, rate-limited or unavailable. A synthetic fallback is explicitly labelled and must never be described as a live quote.

## What's upgraded in this version

- Live quote adapter chain: Yahoo Finance chart endpoint (no key) → Alpha Vantage (API key) → visibly labelled synthetic fallback.
- Live news search: GDELT DOC 2.0 recent article search (no API key), with article titles, domains, timestamps and source links passed into the News Agent, Bull and Bear.
- Six specialized reasoning roles call the Gemini Interactions API when `GEMINI_API_KEY` is configured. Each event records its actual provider and whether live model reasoning was used. Without credentials or when the model fails, deterministic fallback text is clearly identified.
- Optional Lyzr agent routing per role using `LYZR_AGENT_IDS` JSON. If a role has no Lyzr agent ID, the Gemini Interactions API is used; the single `LYZR_AGENT_ID` is used only for the Chair.
- BAND sends real mention-routed messages using each sender's Agent API key. The audit distinguishes delivered BAND messages from local-only handoffs. BAND's remote agents must be registered and in the room; this app does not falsely claim that a message was received or processed by a remote peer.
- Finch-compatible reusable skill files for market research and risk review are loaded by the local agents and included under `backend/app/skills` and `finch_skills/` for import/adaptation.
- AdaL report webhook with explicit delivery errors.
- Agent37-ready FastAPI service entrypoint and Dockerfile/Procfile; deployment itself must be performed in your Agent37 workspace.
- SQLite audit history, paper-trade ledger, evidence provenance panel, data caveats and integration health endpoint.

## Data providers

### Quotes

The backend attempts `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}` first. If it fails, it tries Alpha Vantage `GLOBAL_QUOTE` if an API key is configured. If neither returns a usable quote, the app returns a synthetic demo quote with `is_demo: true`, `source: Synthetic demo data`, and provider errors. Yahoo's chart endpoint is a convenience data source, not a guaranteed exchange feed; validate the provider's terms, delay and availability before a public deployment.

### News

The backend queries the GDELT DOC 2.0 article search endpoint over a seven-day window. It does not require a key, but is rate-limited and not exhaustive. A zero-result response is not evidence that no relevant news exists. Each returned article is shown with its URL and metadata. If the provider fails, the News Agent receives an explicit unavailable state rather than fabricated headlines.

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

All six local role calls then use the Gemini Interactions API unless a corresponding Lyzr role agent is configured. The report's `model_calls` array and each event's `provider` field show what actually happened. A configured key is not proof a call succeeded; inspect the returned provider for each event.

## Configure BAND

The app uses the BAND Agent API endpoint documented at https://docs.band.ai/api/agent-api.

1. Register the six agents in BAND.
2. Add all six as participants to one shared chat room.
3. Copy the room ID into `BAND_CHAT_ID`.
4. Map each sender role to its own Agent API key in `BAND_AGENT_KEYS`.
5. Map each recipient role to its participant ID, name and handle in `BAND_AGENT_PEERS`.

Example JSON values (replace placeholders; do not commit real keys):

```env
BAND_CHAT_ID=your-room-id
BAND_AGENT_KEYS={"analyst":"key1","news":"key2","bull":"key3","bear":"key4","risk":"key5","chair":"key6"}
BAND_AGENT_PEERS={"analyst":{"id":"participant-id-1","name":"Market Analyst","handle":"marketanalyst"},"news":{"id":"participant-id-2","name":"News Intelligence","handle":"newsintel"},"bull":{"id":"participant-id-3","name":"Bull Advocate","handle":"bulladvocate"},"bear":{"id":"participant-id-4","name":"Bear Challenger","handle":"bearchallenger"},"risk":{"id":"participant-id-5","name":"Risk Guardian","handle":"riskguardian"},"chair":{"id":"participant-id-6","name":"Portfolio Chair","handle":"portfoliochair"}}
```

Messages are sent as directed mentions. The report shows sent vs local-only handoffs. Sending a message is not proof that the remote participant processed it; BAND's WebSocket/message processing lifecycle is a separate remote-agent runtime. For full autonomous remote workers, deploy a worker per registered BAND identity using BAND's WebSocket delivery and message-processing endpoints.

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

## Finch skills

`backend/app/skills/market-research/SKILL.md` and `backend/app/skills/risk-check/SKILL.md` are reusable local skill packages. The local Analyst, News and Risk roles load these instructions at runtime. They are included as source assets; importing/publishing them into the Finch product requires your Finch workspace access and any import process provided by Finch.

## AdaL workflow

Create an AdaL workflow that accepts a JSON webhook. Set its endpoint and optional bearer token:

```env
ADAL_WEBHOOK_URL=https://your-configured-adal-webhook
ADAL_WEBHOOK_TOKEN=your_token_if_required
```

Use **Send to AdaL** in the completed analysis. The API returns an error if no endpoint is configured or delivery fails. The app does not create an AdaL account or workflow on your behalf.

## Agent37 deployment

The FastAPI backend is compatible with a standard Python/uvicorn service and includes `Procfile` and `backend/Dockerfile`. Deploy the backend through your Agent37 workspace using its current runtime instructions, then set `AGENT37_PUBLIC_URL` and `frontend/.env`:

```env
VITE_API_URL=https://your-deployed-api
```

A URL is not considered deployed merely because this variable is present; verify the live service at `/api/health`. No Agent37 deployment is included in this ZIP because it requires your account/workspace.

## API

- `GET /api/health` — configured provider status (not a guarantee of successful live requests)
- `GET /api/agents` — six agent roles
- `GET /api/quote/{symbol}` — quote provider chain and explicit synthetic fallback
- `GET /api/history-prices/{symbol}?range_=1mo&interval=1d` — chart history from Yahoo chart endpoint
- `GET /api/news/{symbol}?company=Company%20Name` — live GDELT article search
- `POST /api/analyze` — six-stage committee run and audit provenance
- `POST /api/paper-trade/{run_id}` — paper BUY only when deterministic risk gate approves
- `GET /api/history` and `GET /api/history/{run_id}` — saved analysis reports
- `GET /api/trades` — paper execution ledger
- `POST /api/adal/notify/{run_id}` — send report to configured AdaL webhook

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
| Lyzr | Per-role inference adapter | Create/deploy Lyzr agents and add API key + IDs |
| Finch | Reusable skill files loaded locally | Import/publish skills in Finch workspace if required by judging |
| AdaL | Report webhook client | Create AdaL workflow and paste webhook URL/token |
| Agent37 | Python service packaging | Deploy to your Agent37 workspace and configure frontend API URL |

## Stack

React, Vite, Recharts, Lucide React, FastAPI, Pydantic, SQLite, Yahoo Finance chart endpoint, Alpha Vantage, GDELT DOC 2.0, Gemini Interactions API, optional Lyzr inference and BAND Agent API.
