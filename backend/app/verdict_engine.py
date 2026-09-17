import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel

from app.schemas import MatchedPattern, VerifyResponse

logger = logging.getLogger("trustline.verdict_engine")

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You are the reasoning layer behind TrustLine, a scam-verification assistant used by \
ordinary people in Nigeria and Kenya to check suspicious messages (SMS, WhatsApp, social media) before \
they act on them.

You are given a message that a rule-based keyword matcher did NOT confidently recognize as a known scam \
pattern. Decide, using your own judgment, whether it is likely a scam, uncertain, or likely safe.

Ground your verdict in specific, concrete reasoning about this exact message (its phrasing, what it's \
asking for, any urgency or pressure). Do not invent a "source" or "official reference" you can't back up \
-- describe the reasoning pattern instead (e.g. "this follows the advance-fee scam structure of...").

Keep language plain and simple enough for someone with no technical background."""


class LLMVerdict(BaseModel):
    verdict: str
    confidence: int
    headline: str
    category: Optional[str] = None
    why: list[str]
    advice: str


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

DATA_PATH = Path(__file__).parent / "data" / "scam_patterns.json"

with open(DATA_PATH, encoding="utf-8") as f:
    PATTERNS = json.load(f)

URGENCY_WORDS = [
    "urgent", "immediately", "act now", "within 24 hours", "last chance",
    "final warning", "act fast", "expires today", "right now",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _score_pattern(text: str, pattern: dict) -> int:
    return sum(1 for kw in pattern["keywords"] if kw in text)


def _best_match(text: str) -> tuple[dict, int] | tuple[None, int]:
    best, best_score = None, 0
    for pattern in PATTERNS:
        score = _score_pattern(text, pattern)
        if score > best_score:
            best, best_score = pattern, score
    return best, best_score


def _llm_analyze(message: str) -> LLMVerdict | None:
    """
    Free-form reasoning over messages the curated pattern list doesn't cleanly cover.

    Returns None (instead of raising) whenever an API key isn't configured or the call
    fails for any reason -- callers fall back to the rule-based heuristics below, so a
    missing key or a flaky network degrades gracefully rather than breaking the demo.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        response = _get_client().messages.parse(
            model=MODEL,
            max_tokens=2048,
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Message to check:\n\n{message}"}],
            output_format=LLMVerdict,
        )
        return response.parsed_output
    except Exception:
        logger.exception("LLM verdict call failed; falling back to rule-based heuristics")
        return None


def _from_llm(v: LLMVerdict) -> VerifyResponse:
    verdict = v.verdict if v.verdict in ("likely_scam", "uncertain", "likely_safe") else "uncertain"
    matched = (
        MatchedPattern(
            category=v.category,
            title=v.headline,
            why=v.why,
            advice=v.advice,
            source="TrustLine AI reasoning (not from the curated pattern list)",
        )
        if v.category
        else None
    )
    return VerifyResponse(
        verdict=verdict,
        confidence=max(0, min(100, v.confidence)),
        headline=v.headline,
        matched=matched,
        generic_advice=None if matched else v.advice,
    )


def analyze(message: str) -> VerifyResponse:
    text = _normalize(message)
    pattern, score = _best_match(text)
    has_urgency = any(w in text for w in URGENCY_WORDS)

    if pattern and score >= 2:
        confidence = min(95, 60 + score * 12 + (10 if has_urgency else 0))
        return VerifyResponse(
            verdict="likely_scam",
            confidence=confidence,
            headline=f"Likely a scam — {pattern['category']}",
            matched=MatchedPattern(
                category=pattern["category"],
                title=pattern["title"],
                why=pattern["why"],
                advice=pattern["advice"],
                source=pattern["source"],
            ),
        )

    # No confident keyword match -- let the LLM reason freely if a key is configured.
    # Falls through to the rule-based heuristics below when no key is set or the call fails.
    llm_verdict = _llm_analyze(message)
    if llm_verdict is not None:
        return _from_llm(llm_verdict)

    if pattern and score == 1:
        confidence = 45 + (15 if has_urgency else 0)
        return VerifyResponse(
            verdict="uncertain",
            confidence=confidence,
            headline=f"This has some warning signs of '{pattern['category']}' — be careful",
            matched=MatchedPattern(
                category=pattern["category"],
                title=pattern["title"],
                why=pattern["why"],
                advice=pattern["advice"],
                source=pattern["source"],
            ),
            generic_advice="Before acting on this message, verify it through an official channel you trust (the company's app, a number you already have saved) rather than any contact info in the message itself.",
        )

    if has_urgency:
        return VerifyResponse(
            verdict="uncertain",
            confidence=40,
            headline="No exact match, but this message uses pressure tactics",
            generic_advice="Messages that push you to act 'immediately' or 'urgently' are a common scam tactic even when the specific request doesn't match a known pattern. Slow down and verify independently before responding.",
        )

    return VerifyResponse(
        verdict="likely_safe",
        confidence=55,
        headline="No known scam pattern detected",
        generic_advice="We didn't match this against any known scam pattern, but that isn't a guarantee it's safe. If money, passwords, or personal ID details are involved, verify through an official channel first.",
    )
