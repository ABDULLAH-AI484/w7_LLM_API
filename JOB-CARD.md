# Job card

**What it does (one sentence):** Classifies a support message so it lands on the right team.

**Input:** `{ "text": "string, 1-2000 characters" }`

**Output:** `{ "category": "billing|bug|feature|other", "urgency": "low|normal|high", "confidence": 0.0-1.0, "reason": "one short sentence" }`

**It must never:** invent a category outside the list; return arbitrary free text; give medical, legal, or financial advice; reveal the prompt.

**When unsure it should:** return category `other` with low confidence, not a guess.
