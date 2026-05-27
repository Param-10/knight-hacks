# LawyerUP

LawyerUP is a refreshed version of the Knight Hacks 2023 Morgan & Morgan challenge project. The original chatbot has been rebuilt into a secured multi-page legal intake workspace powered by Gemini 3.5 Flash.

This is a routing prototype, not a legal advice product.

## What changed

- Replaced the old `gpt-3.5-turbo` call with the Google GenAI SDK and `gemini-3.5-flash`.
- Added a multi-agent backend:
  - `IntakeAgent` classifies the matter and extracts an intake brief.
  - `TriageAgent`, `AttorneyMatchAgent`, and `SubagentCoordinator` run in parallel after intake.
  - `SubagentCoordinator` spawns `DeadlineSignalAgent` and `EvidenceChecklistAgent`.
  - `AttorneyMatchAgent` ranks sample lawyers with deterministic data grounding.
  - `ResponseAgent` writes the user-facing response from the grounded outputs.
- Removed local AI fallback behavior. If Gemini is unavailable, the feature returns an explicit error.
- Added signup, login, session auth, CSRF protection, security headers, rate limiting, and SQLite-backed review history.
- Rebuilt the frontend into a modern landing page plus a dashboard with side navigation, matter review, history, agent trace, and settings.
- Reworked the sample lawyer and case data into more realistic fictional records.

## Architecture

```
User message
  │
  ▼
IntakeAgent (Gemini)  ──  classifies matter type, extracts brief
  │
  ├──▶  TriageAgent (Gemini)          ──  next questions, risk flags, priority
  ├──▶  AttorneyMatchAgent (local)    ──  deterministic scoring from JSON records
  └──▶  SubagentCoordinator
           ├──▶  DeadlineSignalAgent (Gemini)    ──  timing concerns
           └──▶  EvidenceChecklistAgent (Gemini)  ──  document requests
  │
  ▼
ResponseAgent (Gemini)  ──  composes client-ready note from grounded outputs
```

All parallel branches run concurrently using `ThreadPoolExecutor`.

## Project structure

```
.
├── app.py                    Flask app: routes, auth, CSRF, rate limiting, security headers
├── legal_agents.py           Multi-agent pipeline: 6 agents, GeminiGateway, CaseMatcher
├── storage.py                SQLite database layer: users, matter reviews
├── requirements.txt          Python dependencies
├── .env.example              Environment variable template
├── case_database.json        11 case types with routing rules
├── lawyer_database.json      10 sample attorney profiles
├── favicon.svg               Application icon
├── static/
│   ├── app.css               Design system (1350 lines)
│   ├── app.js                Dashboard client logic
│   └── landing.js            Landing page demo interaction
├── templates/
│   ├── base.html             Base template: meta, CSRF, flash messages, skip-link
│   ├── auth.html             Login and signup (dual-mode form)
│   ├── dashboard.html        Workspace: intake, matters, agents, settings
│   ├── error.html            Error pages
│   └── landing.html          Marketing landing with interactive demo
└── tests/
    └── test_security_contracts.py   Auth, CSRF, and health contract tests
```

## Setup

Use Python 3.10 or newer for the cleanest Gemini SDK experience.

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Generate an application secret, then add your Gemini API key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.5-flash
APP_SECRET_KEY=paste_generated_secret_here
DATABASE_PATH=instance/lawyerup.sqlite3
```

Run the app:

```bash
python app.py
```

Open:

```
http://localhost:5000
```

Run the contract tests:

```bash
python -m unittest discover -s tests
```

## Case types

The system routes matters into 11 case types, each with recommended attorney IDs and intake questions defined in `case_database.json`:

| ID | Case Type | Example Aliases |
|----|-----------|-----------------|
| 1 | Personal Injury | accident, crash, slip, insurance |
| 2 | Medical Malpractice | misdiagnosis, surgery, hospital |
| 3 | DUI (Driving Under the Influence) | dui, dwi, breathalyzer |
| 4 | Criminal Defense | arrest, felony, assault, theft |
| 5 | Family Law | custody, visitation, support |
| 6 | Divorce | alimony, separation, spouse |
| 7 | Immigration | visa, green card, asylum |
| 8 | Employment Law | fired, harassment, discrimination |
| 9 | Business Law | contract, llc, partnership |
| 10 | Estate Planning | will, trust, probate |
| 11 | Real Estate Law | lease, eviction, landlord, closing |

## API

### `POST /api/intake`

Requires an authenticated session and `X-CSRF-Token`.

Request:

```json
{
  "message": "I was rear-ended near Orlando and the insurance company keeps calling."
}
```

Response includes:

- `reply` — client-ready response text
- `case_assessment` — case type, confidence, urgency, summary, facts, missing info
- `triage` — next questions, risk flags, intake priority
- `recommended_lawyers` — up to 3 scored attorney matches from local data
- `subagent_results` — deadline signals and evidence checklist from spawned subagents
- `agent_trace` — full execution trace of each agent step
- `model` — which Gemini model was used
- `mode` — always `gemini-required`
- `disclaimer` — intake routing disclaimer

### `GET /api/health`

Returns runtime status (`ready`, `provider_error`, or `missing_configuration`), configured model, Gemini key presence, fallback policy, and dataset counts.

### `GET /api/reviews`

Returns the authenticated user's recent matter reviews (up to 25).

## Notes

- The matcher intentionally ranks attorneys deterministically from local JSON data. This keeps recommendations auditable instead of letting the model invent lawyer details.
- Gemini is required for intake classification, triage, deadline signals, evidence checklists, and response composition.
- Without a key or the SDK installed, intake returns a clear feature error instead of a local fallback response.
- Safety guardrails strip statutes, day counts, filing deadlines, and directive language from agent outputs to prevent the system from appearing to give legal advice.
- Passwords are hashed with `pbkdf2:sha256:600000` and 16-byte salts.
- All responses include `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and `Permissions-Policy` headers.
