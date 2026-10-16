"""Classify what the parent said in reply to a reminder.

This never answers a medical question. It only decides one of:
taken | snooze | symptom | confused | unknown
Symptom and confused replies are passed to the family, not answered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

SYMPTOM_WORDS = [
    "chakkar", "chakar", "dard", "ulti", "ghabra", "saans", "sans phool", "seene", "chhati", "chhaati",
    "behosh", "kamzori", "kamjori", "bukhar", "pareshan", "bimar", "bimaar", "dikkat", "takleef", "taklif",
    "hospital", "emergency", "madad", "bachao", "chest", "dizzy", "pain", "vomit", "faint",
    "चक्कर", "दर्द", "उल्टी", "घबराहट", "सांस", "साँस", "सीने", "छाती", "बेहोश", "कमजोरी", "बुखार",
    "परेशान", "बीमार", "दिक्कत", "तकलीफ", "अस्पताल", "मदद",
]
_RE_TABIYAT_BAD = re.compile(
    r"tabi(?:y|i)at\s*(?:kharab|theek nahi|thik nahi|acchi nahi|accha nahi|sahi nahi)"
    r"|तबी(?:य|इ)त\s*(?:खराब|ठीक नहीं)"
)
CONFUSED_WORDS = [
    "kaun si", "kaunsi", "kaun sa", "kya lena", "kya khana", "yaad nahi", "bhool", "samajh nahi", "kitni goli",
    "kitni dawai", "kitna lun", "which one", "i forgot", "dont remember",
    "कौन सी", "कौनसी", "कौन सा", "याद नहीं", "भूल", "समझ नहीं", "कितनी",
]
SNOOZE_PHRASES = [
    "baad mein", "baad me", "baad main", "thodi der", "thodi der mein", "abhi nahi", "abhi nahin", "ruko",
    "ruk jao", "ruk ja", "later", "not now", "wait", "minute", "mins", "ghanta", "ghante",
    "बाद में", "बाद मे", "थोड़ी देर", "अभी नहीं", "रुको", "मिनट", "घंटा", "घंटे",
]
TAKEN_PHRASES = [
    "kha li", "kha liya", "khaa li", "kha chuka", "kha chuki", "le li", "le liya", "lee li", "le chuka",
    "le chuki", "ho gaya", "hogaya", "i took", "already took", "taken it", "have taken",
    "खा ली", "खा लिया", "ले ली", "ले लिया", "हो गया", "ठीक है",
    "theek hai", "thik hai",
]
TAKEN_TOKENS = {"haan", "han", "ha", "haa", "hanji", "haanji", "yes", "ok", "okay", "done", "taken", "हाँ", "हां", "हा", "जी"}
NEGATION_TOKENS = {"nahi", "nahin", "nhi", "nahee", "नहीं", "नही", "mat", "no"}

_NUM_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "pandrah": 15, "bees": 20, "tees": 30, "chalis": 40, "pachas": 50,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9,
    "दस": 10, "पंद्रह": 15, "बीस": 20, "तीस": 30,
}


@dataclass
class Reply:
    outcome: str  # taken | snooze | symptom | confused | unknown
    snooze_min: int = 10
    note: str = ""


def _snooze_minutes(text: str) -> int:
    m = re.search(r"(\d+)\s*(?:minute|min|mins|मिनट)", text)
    if m:
        return max(2, min(60, int(m.group(1))))
    m = re.search(r"(\d+)\s*(?:ghanta|ghante|hour|hours|घंटा|घंटे)", text)
    if m:
        return max(2, min(60, int(m.group(1)) * 60))
    for word, n in _NUM_WORDS.items():
        if re.search(rf"(?:^|\s){re.escape(word)}\s*(?:minute|min|mins|मिनट)", text):
            return max(2, min(60, n))
    if re.search(r"aadha\s*ghanta|आधा\s*घंटा|half\s*hour", text):
        return 30
    if re.search(r"ek\s*ghanta|एक\s*घंटा|an\s*hour|one\s*hour", text):
        return 60
    return 10


def classify_reply(text: str) -> Reply:
    t = re.sub(r"\s+", " ", (text or "").translate(_DEVANAGARI_DIGITS).lower()).strip()
    if not t:
        return Reply("unknown")

    if any(w in t for w in SYMPTOM_WORDS) or _RE_TABIYAT_BAD.search(t):
        return Reply("symptom")
    if any(w in t for w in CONFUSED_WORDS):
        return Reply("confused")

    tokens = set(re.findall(r"[\wऀ-ॿ]+", t))
    if any(p in t for p in SNOOZE_PHRASES):
        return Reply("snooze", _snooze_minutes(t))
    if tokens & NEGATION_TOKENS:
        return Reply("snooze", 10, note="declined")
    if any(p in t for p in TAKEN_PHRASES) or tokens & TAKEN_TOKENS:
        return Reply("taken")
    # Prisma sometimes hears "kha li" as "khali"
    if re.search(r"\bkhali\b(?!\s*pet)", t):
        return Reply("taken")
    return Reply("unknown")
