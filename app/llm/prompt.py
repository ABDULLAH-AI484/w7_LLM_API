from pathlib import Path

PROMPT_VERSION = "triage-v1"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "triage-v1.md"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")
