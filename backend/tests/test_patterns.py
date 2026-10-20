import json
from pathlib import Path

import pytest

from app import triage, verdict_engine

PID = "fake_online_vendor_pay_first"
DATA = Path(__file__).resolve().parent.parent / "app" / "data"

VENDOR_MESSAGES = [
    "Fresh foodstuff available: yam, garri, beans, rice. Payment before delivery please. Chat me on WhatsApp wa.me/2348012345678 to order. Delivery within 24 hours.",
    "Hello, I sell bulk foodstuff at wholesale prices. Pay first to confirm your order, then we deliver tomorrow. Message me on WhatsApp.",
    "Drop your order on WhatsApp. We operate pay before delivery, no refund, no delivery without payment first.",
]

LEGITIMATE = [
    "We offer pay on delivery within Lagos. Visit our shop at 12 Allen Avenue, Ikeja, open Monday to Saturday.",
    "Hi, are we still meeting for lunch tomorrow at one?",
]


@pytest.mark.parametrize("message", VENDOR_MESSAGES)
def test_fake_vendor_messages_are_flagged_without_the_ai(message):
    result = verdict_engine.analyze(message, "en")
    assert result.verdict == "likely_scam" and result.confidence >= 70
    assert result.matched and result.matched.category_en == "Fake online vendor (pay first, then vanishes)"


@pytest.mark.parametrize("message", LEGITIMATE)
def test_ordinary_sellers_and_chat_are_not_flagged(message):
    assert verdict_engine.analyze(message, "en").verdict != "likely_scam"


def test_the_verdict_is_translated():
    fr = verdict_engine.analyze(VENDOR_MESSAGES[0], "fr").matched
    assert fr.title.startswith("Un vendeur en ligne") and fr.category_en.startswith("Fake online vendor")
    sw = verdict_engine.analyze(VENDOR_MESSAGES[0], "sw").matched
    assert sw.title.startswith("Muuzaji wa mtandaoni")


@pytest.mark.parametrize("lang", ["fr", "sw", "yo", "ha"])
def test_every_language_has_the_pattern(lang):
    data = json.loads((DATA / f"scam_patterns_{lang}.json").read_text(encoding="utf-8"))
    entry = data[PID]
    assert entry["title"] and entry["category"] and entry["advice"] and len(entry["why"]) == 2


def test_group_monitoring_treats_these_messages_as_worth_checking():
    assert all(triage.has_risk_signals(m) for m in VENDOR_MESSAGES)
