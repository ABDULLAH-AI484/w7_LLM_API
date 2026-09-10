# Support Triage API — Week 7 Assignment

This project adds one narrow AI feature: send one messy customer-support message to `POST /triage`, and receive one clean JSON decision that downstream code can trust. The endpoint validates input before any model call, asks an OpenAI-compatible provider using a versioned prompt, validates the model's response with Pydantic, repairs one invalid response, quarantines a second failure, and never returns raw model text.

## Quick start (stub mode, no API key)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The default `.env.example` uses `LLM_STUB=1`, so this is safe to run without spending quota.

```bash
curl -s http://127.0.0.1:8000/triage \
  -H 'Content-Type: application/json' \
  -d '{"text":"I was charged twice for my monthly plan."}'
```

Exact stub response:

```json
{"category":"other","urgency":"normal","confidence":0.2,"reason":"Stub mode is enabled for local testing."}
```

Deliberately invalid request:

```bash
curl -s -X POST http://127.0.0.1:8000/triage \
  -H 'Content-Type: application/json' -d '{}'
```

It returns HTTP 422 and a validation detail naming `text`. FastAPI uses 422 for request-schema validation; the model-output failure path uses the assignment-required 422 as well.

## Job card

See [JOB-CARD.md](JOB-CARD.md). The closed categories are `billing`, `bug`, `feature`, and `other`; urgency is `low`, `normal`, or `high`.

## Provider setup

The code uses the OpenAI Python client against any OpenAI-compatible endpoint. To use OpenRouter, set `LLM_STUB=0`, put a key in `.env`, and keep:

```dotenv
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openrouter/free
LLM_API_KEY=your-key-here
```

To use Ollama instead, change only these three values:

```dotenv
LLM_BASE_URL=http://localhost:11434/v1/
LLM_MODEL=gemma3:1b
LLM_API_KEY=ollama
```

The provider is deliberately configured through the three environment variables rather than hard-coded. The client sets an explicit 30-second timeout, disables the SDK's hidden retries, and retries only timeouts, connection failures, 429s, and 5xx responses with bounded exponential backoff and jitter. It does not retry 400, 401, or 403 responses.

## Safety and reliability behavior

- `LLM_STUB=1` skips the model and returns a schema-valid deterministic test object.
- `LLM_ENABLED=false` is the kill switch; it skips the provider and uses a deterministic keyword fallback.
- Model output is parsed from plain JSON or a JSON code fence and validated with Pydantic.
- An invalid result gets exactly one repair attempt. A second failure returns 422 and writes `logs/quarantine.jsonl`.
- Each successful model call writes prompt version, model, token counts, duration, and repair count to `logs/llm-calls.jsonl`.
- User content is JSON-encoded in a separate user message and is never placed in the system prompt.

## Eval

The eight hand-labelled cases are in `evals/cases.json`. Run the local deterministic eval with:

```bash
LLM_STUB=0 LLM_ENABLED=false python eval.py
```

On 2026-09-10, the deterministic fallback scored **8/8 (100%)** on `triage-v1`. A real-provider score should be recorded after running `python eval.py` with a configured provider; it is intentionally not fabricated here because this environment has no user-supplied provider key.

## Tests

```bash
pytest -q
```

## Cost note

The local stub and kill switch cost $0. A real call's token usage is recorded in `logs/llm-calls.jsonl`; provider pricing varies by model. At 10,000 requests/day, the largest cost drivers are output tokens and repair/retry calls, so the schema, low temperature, bounded retries, and kill switch are intentional.

## What I would fix with another day

I would add provider-specific integration tests using a mock OpenAI-compatible server and expand the eval set to 25 cases split into easy and ambiguous examples.
