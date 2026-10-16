import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel

from app import limits
from app.i18n import LANG_NAMES, normalize_lang, t
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


def _system_prompt(lang: str) -> str:
    # Always name the answer language explicitly: without it Claude mirrors the language of the
    # pasted message, which mixes languages on screen when it differs from the interface language.
    language = LANG_NAMES.get(lang, "English")
    return (
        SYSTEM_PROMPT
        + f"\n\nIMPORTANT: Write every text field (headline, category, why, advice) in natural, clear "
        f"{language} suited to everyday readers, even if the message you are checking is written in a "
        "different language. The `verdict` field must still be exactly one of the English values: "
        "likely_scam, uncertain, likely_safe."
    )


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


DATA_DIR = Path(__file__).parent / "data"

with open(DATA_DIR / "scam_patterns.json", encoding="utf-8") as f:
    PATTERNS = json.load(f)

TRANSLATED_PATTERNS: dict[str, dict] = {}
for _lang in LANG_NAMES:
    with open(DATA_DIR / f"scam_patterns_{_lang}.json", encoding="utf-8") as f:
        TRANSLATED_PATTERNS[_lang] = json.load(f)

URGENCY_WORDS = [
    "urgent", "immediately", "act now", "within 24 hours", "last chance",
    "final warning", "act fast", "expires today", "right now",
    "immédiatement", "d'urgence", "agissez maintenant", "dans les 24 heures",
    "dernière chance", "expire aujourd'hui", "tout de suite", "sans tarder",
    "mara moja", "kwa dharura", "ndani ya saa 24", "nan da nan", "cikin gaggawa",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _score_pattern(text: str, pattern: dict) -> int:
    keywords = list(pattern["keywords"])
    for translated in TRANSLATED_PATTERNS.values():
        keywords += translated.get(pattern["id"], {}).get("keywords", [])
    return sum(1 for kw in keywords if kw in text)


def _best_match(text: str) -> tuple[dict, int] | tuple[None, int]:
    best, best_score = None, 0
    for pattern in PATTERNS:
        score = _score_pattern(text, pattern)
        if score > best_score:
            best, best_score = pattern, score
    return best, best_score


def category_labels(lang: str) -> dict[str, str]:
    """English category name -> its label in `lang`, for translating community stats."""
    translated = TRANSLATED_PATTERNS.get(lang, {})
    return {p["category"]: translated[p["id"]]["category"] for p in PATTERNS if p["id"] in translated}


def _matched(pattern: dict, lang: str) -> MatchedPattern:
    localized = TRANSLATED_PATTERNS.get(lang, {}).get(pattern["id"])
    source = localized or pattern
    return MatchedPattern(
        category=source["category"],
        category_en=pattern["category"],
        title=source["title"],
        why=source["why"],
        advice=source["advice"],
        source=pattern["source"],
    )


def _llm_analyze(message: str, lang: str) -> LLMVerdict | None:
    """
    Free-form reasoning over messages the curated pattern list doesn't cleanly cover.

    Returns None (instead of raising) whenever an API key isn't configured or the call
    fails for any reason -- callers fall back to the rule-based heuristics below, so a
    missing key or a flaky network degrades gracefully rather than breaking the demo.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    if not limits.consume_llm_call():
        logger.warning("Daily AI-call ceiling reached; using rule-based fallback")
        return None
    try:
        response = _get_client().messages.parse(
            model=MODEL,
            max_tokens=2048,
            output_config={"effort": "low"},
            system=_system_prompt(lang),
            messages=[{"role": "user", "content": f"Message to check:\n\n{message}"}],
            output_format=LLMVerdict,
        )
        return response.parsed_output
    except Exception:
        logger.exception("LLM verdict call failed; falling back to rule-based heuristics")
        return None


def _from_llm(v: LLMVerdict, lang: str) -> VerifyResponse:
    verdict = v.verdict if v.verdict in ("likely_scam", "uncertain", "likely_safe") else "uncertain"
    matched = (
        MatchedPattern(
            category=v.category,
            title=v.headline,
            why=v.why,
            advice=v.advice,
            source=t(lang, "ai_source"),
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


def analyze(message: str, language: str = "en") -> VerifyResponse:
    lang = normalize_lang(language)
    text = _normalize(message)
    pattern, score = _best_match(text)
    has_urgency = any(w in text for w in URGENCY_WORDS)

    if pattern and score >= 2:
        confidence = min(95, 60 + score * 12 + (10 if has_urgency else 0))
        matched = _matched(pattern, lang)
        return VerifyResponse(
            verdict="likely_scam",
            confidence=confidence,
            headline=t(lang, "likely_scam", category=matched.category),
            matched=matched,
        )

    # No confident keyword match -- let the LLM reason freely if a key is configured.
    # Falls through to the rule-based heuristics below when no key is set or the call fails.
    llm_verdict = _llm_analyze(message, lang)
    if llm_verdict is not None:
        return _from_llm(llm_verdict, lang)

    if pattern and score == 1:
        confidence = 45 + (15 if has_urgency else 0)
        matched = _matched(pattern, lang)
        return VerifyResponse(
            verdict="uncertain",
            confidence=confidence,
            headline=t(lang, "weak_match", category=matched.category),
            matched=matched,
            generic_advice=t(lang, "verify_officially"),
        )

    if has_urgency:
        return VerifyResponse(
            verdict="uncertain",
            confidence=40,
            headline=t(lang, "pressure_headline"),
            generic_advice=t(lang, "pressure_advice"),
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        # A key is configured, so reaching here means the AI call failed -- never tell the user "safe" in that case.
        return VerifyResponse(
            verdict="uncertain",
            confidence=0,
            headline=t(lang, "ai_failed_headline"),
            generic_advice=t(lang, "ai_failed_advice"),
        )

    return VerifyResponse(
        verdict="likely_safe",
        confidence=55,
        headline=t(lang, "safe_headline"),
        generic_advice=t(lang, "safe_advice"),
    )
