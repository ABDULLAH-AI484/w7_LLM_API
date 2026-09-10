import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .llm.client import LLMClient, ModelResponse
from .llm.prompt import PROMPT_VERSION, load_system_prompt
from .llm.schema import Category, TriageRequest, TriageResult, Urgency

load_dotenv()
app = FastAPI(title="Support Triage API", version="1.0.0")
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
COST_LOG = LOG_DIR / "llm-calls.jsonl"
QUARANTINE_LOG = LOG_DIR / "quarantine.jsonl"


def _write_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def _fallback(text: str) -> TriageResult:
    lowered = text.lower()
    if any(word in lowered for word in ("refund", "invoice", "charge", "billing", "payment")):
        return TriageResult(category=Category.billing, urgency=Urgency.normal, confidence=0.78, reason="The message concerns billing or payment.")
    if any(word in lowered for word in ("crash", "error", "bug", "broken", "cannot log in")):
        return TriageResult(category=Category.bug, urgency=Urgency.high, confidence=0.78, reason="The message reports a product problem.")
    if any(word in lowered for word in ("add", "would like", "feature", "support", "request")):
        return TriageResult(category=Category.feature, urgency=Urgency.low, confidence=0.65, reason="The message appears to request a product change.")
    return TriageResult(category=Category.other, urgency=Urgency.normal, confidence=0.35, reason="The message does not clearly fit another category.")


def _extract_json(raw: str) -> Any:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _validate(raw: str) -> TriageResult:
    return TriageResult.model_validate(_extract_json(raw))


def _validation_error(exc: Exception) -> str:
    return str(exc)[:1200]


async def _model_result(request: TriageRequest) -> TriageResult:
    load_dotenv(override=True)
    client = LLMClient()
    system_prompt = load_system_prompt()
    raw = ""
    error = ""
    for repair_count in (0, 1):
        if repair_count == 0:
            response = await client.complete(system_prompt, request.text)
        else:
            repair_prompt = (
                system_prompt
                + "\n\nYour previous answer was rejected for this reason:\n"
                + error
                + "\nPrevious output:\n"
                + raw
                + "\nReturn only corrected JSON matching the schema."
            )
            response = await client.complete(repair_prompt, request.text)
        raw = response.text
        try:
            result = _validate(raw)
            _write_jsonl(COST_LOG, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "prompt_version": PROMPT_VERSION,
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "duration_ms": response.duration_ms,
                "repair_count": repair_count,
            })
            return result
        except Exception as exc:
            error = _validation_error(exc)
            if repair_count == 0:
                continue
            _write_jsonl(QUARANTINE_LOG, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "prompt_version": PROMPT_VERSION,
                "input": request.model_dump(),
                "raw_output": raw,
                "error": error,
            })
            raise HTTPException(status_code=422, detail="Model output failed schema validation after one repair attempt.") from exc
    raise HTTPException(status_code=422, detail="Model output could not be validated.")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/triage", response_model=TriageResult)
async def triage(request: TriageRequest) -> TriageResult | JSONResponse:
    if os.getenv("LLM_ENABLED", "true").lower() == "false":
        return _fallback(request.text)
    if os.getenv("LLM_STUB", "0") == "1":
        return TriageResult(category=Category.other, urgency=Urgency.normal, confidence=0.2, reason="Stub mode is enabled for local testing.")
    try:
        return await _model_result(request)
    except HTTPException:
        raise
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            raise HTTPException(status_code=502, detail="LLM authentication or permission failed; no retry was attempted.") from exc
        if "timeout" in str(exc).lower():
            raise HTTPException(status_code=504, detail="LLM request timed out.") from exc
        raise HTTPException(status_code=502, detail="LLM provider request failed.") from exc
