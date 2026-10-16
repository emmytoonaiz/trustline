import re

from app import verdict_engine

# Group comments are mostly harmless ("nice dress!", "how much?"). A full check costs an AI call
# and several seconds, so only messages that carry at least one risk signal get one.
_URL = re.compile(r"(https?://|www\.|t\.me/|bit\.ly|wa\.me|\b[a-z0-9-]+\.(com|ng|ke|xyz|top|click|link|site|online)\b)", re.I)
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s-]{8,}\d)(?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)\d{10}(?!\d)")
_MONEY = re.compile(r"([₦$€£]\s?\d|\bkes\s?\d|\bngn\s?\d|\b\d[\d,]*\s?(naira|ksh|usd|dollars)\b)", re.I)

_WORDS = [
    # contact / move the conversation away
    "dm me", "inbox me", "whatsapp", "telegram", "contact me", "call me", "text me", "message me",
    # money and credentials
    "send money", "transfer", "account number", "bvn", "otp", "pin", "password", "refund", "deposit",
    "loan", "invest", "crypto", "bitcoin", "forex", "giveaway", "winner", "claim", "prize", "free",
    # impersonation
    "customer care", "customer service", "official", "support team", "admin",
    # urgency
    "urgent", "immediately", "act now", "limited time", "hurry",
    # other languages
    "envoyez", "virement", "gagnant", "urgent", "tuma pesa", "bure", "mshindi", "aika kuɗi", "kyauta",
    "fi owó ránṣẹ́", "ọ̀fẹ́",
]


def has_risk_signals(text: str) -> bool:
    lowered = text.lower()
    if _URL.search(lowered) or _PHONE.search(text) or _ACCOUNT.search(text) or _MONEY.search(text):
        return True
    if any(w in lowered for w in _WORDS):
        return True
    _, score = verdict_engine._best_match(verdict_engine._normalize(text))
    return score >= 1
