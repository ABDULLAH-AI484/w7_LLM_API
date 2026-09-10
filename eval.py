import json
import os
import sys
from pathlib import Path

from app.main import app
from fastapi.testclient import TestClient

cases = json.loads(Path("evals/cases.json").read_text())
matched = 0
failures = []

if os.getenv("API_URL"):
    import httpx
    client = httpx.Client(base_url=os.environ["API_URL"], timeout=10)
else:
    client = TestClient(app)

with client:
    for index, case in enumerate(cases, 1):
        response = client.post("/triage", json={"text": case["text"]})
        actual = response.json().get("category") if response.is_success else None
        if actual == case["category"]:
            matched += 1
        else:
            failures.append({"case": index, "expected": case["category"], "actual": actual, "status": response.status_code})
print(json.dumps({"matched": matched, "total": len(cases), "score": f"{matched}/{len(cases)}", "failures": failures}, indent=2))
sys.exit(0 if matched == len(cases) else 1)
