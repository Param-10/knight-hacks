# LawyerUP

LawyerUP is a refreshed version of the Knight Hacks 2023 Morgan & Morgan challenge project. The original chatbot has been rebuilt into a small multi-agent legal intake console powered by Gemini 3.5 Flash.

This is a routing prototype, not a legal advice product.

## What changed

- Replaced the old `gpt-3.5-turbo` call with the Google GenAI SDK and `gemini-3.5-flash`.
- Added a multi-agent backend:
  - `IntakeAgent` classifies the matter and extracts an intake brief.
  - `TriageAgent` identifies missing facts, priority, and risk signals.
  - `AttorneyMatchAgent` ranks sample lawyers with deterministic data grounding.
  - `ResponseAgent` writes the user-facing response from the grounded outputs.
- Added local fallback behavior so the demo still works without an API key.
- Rebuilt the frontend into a clean legal intake workspace with matter snapshot, questions, attorney matches, and agent trace.
- Reworked the sample lawyer and case data into more realistic fictional records.

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

Add your Gemini API key:

```bash
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.5-flash
```

Run the app:

```bash
python app.py
```

Open:

```text
http://localhost:5000
```

## API

### `POST /chat`

Request:

```json
{
  "message": "I was rear-ended near Orlando and the insurance company keeps calling."
}
```

Response includes:

- `reply`
- `case_assessment`
- `triage`
- `recommended_lawyers`
- `agent_trace`
- `model`
- `mode`

### `GET /api/health`

Returns runtime status, configured model, Gemini key presence, and dataset counts.

## Notes

- The matcher intentionally ranks attorneys deterministically from local JSON data. This keeps recommendations auditable instead of letting the model invent lawyer details.
- Gemini is used for classification, triage phrasing, and response composition when `GEMINI_API_KEY` is available.
- Without a key or the SDK installed, the same routes work in `local-fallback` mode.
