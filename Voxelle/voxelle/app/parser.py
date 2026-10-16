"""Rule-based parser: Hindi / Hinglish / English speech -> structured medicine schedule.

No LLM involved. The family always confirms the result (read-back) before it is saved,
so a wrong parse gets caught by a person, not trusted blindly.
"""
from __future__ import annotations

import re

SLOT_KEYWORDS = {
    "subah": {"subah", "subha", "savere", "sawere", "morning", "सुबह", "सवेरे"},
    "dopahar": {"dopahar", "dupahar", "afternoon", "दोपहर", "दुपहर"},
    "shaam": {"shaam", "sham", "evening", "शाम"},
    "raat": {"raat", "night", "रात"},
}
TOKEN_TO_SLOT = {tok: slot for slot, toks in SLOT_KEYWORDS.items() for tok in toks}

DEFAULT_TIMES = {"subah": "08:00", "dopahar": "13:00", "shaam": "18:00", "raat": "21:00"}

CONNECTORS = {"aur", "phir", "fir", "then", "and", "और", "फिर", "तथा", "also", "saath", "plus"}

KIND_TO_ROMAN = {
    "goli": "goli", "goliyan": "goli", "goliya": "goli", "गोली": "goli", "गोलियां": "goli", "गोलियाँ": "goli",
    "dawai": "dawai", "dawa": "dawai", "dawaai": "dawai", "davai": "dawai", "dawaiyan": "dawai",
    "medicine": "dawai", "दवाई": "dawai", "दवा": "dawai", "दवाइयां": "dawai",
    "tablet": "tablet", "tab": "tablet", "टैबलेट": "tablet",
    "capsule": "capsule", "कैप्सूल": "capsule",
    "syrup": "syrup", "सिरप": "syrup",
    "injection": "injection", "इंजेक्शन": "injection",
}

HINDI_NUMBERS = {
    "ek": 1, "एक": 1, "do": 2, "दो": 2, "teen": 3, "तीन": 3, "char": 4, "chaar": 4, "चार": 4,
    "paanch": 5, "panch": 5, "पांच": 5, "पाँच": 5, "chhe": 6, "chah": 6, "chhah": 6, "छह": 6, "छः": 6,
    "saat": 7, "सात": 7, "aath": 8, "आठ": 8, "nau": 9, "नौ": 9, "das": 10, "दस": 10,
    "gyarah": 11, "ग्यारह": 11, "barah": 12, "बारह": 12,
}

STOP_WORDS = {
    "ko", "se", "ke", "ki", "ka", "baad", "bad", "pehle", "pahle", "khane", "khaane", "khana", "khaana",
    "dena", "dijiye", "do", "de", "lena", "lo", "hai", "hain", "papa", "pitaji", "mummy", "mom", "dad",
    "maa", "ma", "unko", "inko", "unhe", "ye", "yeh", "wo", "woh", "for", "the", "a", "to", "take", "give",
    "ko.", "ke.", "ji", "baje", "bje", "time", "par", "pe", "mein", "me", "bhi", "roz", "daily", "everyday",
    "को", "से", "के", "की", "का", "बाद", "पहले", "खाने", "देना", "लेना", "है", "हैं", "पापा", "मम्मी", "बजे",
}
STOP_WORDS |= set(TOKEN_TO_SLOT) | CONNECTORS

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_FOOD_WORD = (
    r"(?:khane|khaane|khana|khaana|khaye|खाने|खाना|food|meal|nashte|nashta|नाश्ते|नाश्ता|"
    r"breakfast|lunch|dinner)"
)
_RE_FOOD_BEFORE = re.compile(
    rf"{_FOOD_WORD}\s*(?:se|ke|से|के)?\s*(?:pehle|pahle|पहले|before)"
    rf"|before\s*{_FOOD_WORD}|khali\s*pet|खाली\s*पेट|empty\s*stomach"
)
_RE_FOOD_AFTER = re.compile(
    rf"{_FOOD_WORD}\s*(?:ke|के)?\s*(?:baad|bad|बाद|after)|after\s*{_FOOD_WORD}"
)
_MEAL_TO_SLOT = {
    "breakfast": "subah", "nashta": "subah", "nashte": "subah", "नाश्ता": "subah", "नाश्ते": "subah",
    "lunch": "dopahar", "dinner": "raat",
}

_NUM_WORDS_RE = "|".join(sorted(map(re.escape, HINDI_NUMBERS), key=len, reverse=True))
_BAJE = r"(?:baje|bje|bajey|बजे)"
_RE_TIME_COLON = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.?|p\.m\.?)?\s*" + _BAJE + r"?")
_RE_TIME_AMPM = re.compile(r"(?<![\d:])(\d{1,2})\s*(am|pm|a\.m\.?|p\.m\.?)(?![a-z])")
_RE_TIME_BAJE = re.compile(r"(?<![\d:])(\d{1,2})\s*" + _BAJE)
_RE_TIME_WORD = re.compile(rf"(?:^|\s)({_NUM_WORDS_RE})\s*" + _BAJE)


def _normalize(text: str) -> str:
    t = text.translate(_DEVANAGARI_DIGITS).lower().strip()
    t = t.replace("।", ". ").replace("|", ". ")
    t = re.sub(r"\bsone\s+se\s+pehle\b|सोने\s+से\s+पहले", " raat ", t)
    return re.sub(r"\s+", " ", t)


def _sub_food(t: str) -> str:
    def before(m: re.Match) -> str:
        return " " + _meal_slot_token(m.group(0)) + " __fbefore__ "

    def after(m: re.Match) -> str:
        return " " + _meal_slot_token(m.group(0)) + " __fafter__ "

    t = _RE_FOOD_BEFORE.sub(before, t)
    return _RE_FOOD_AFTER.sub(after, t)


def _meal_slot_token(phrase: str) -> str:
    for word, slot in _MEAL_TO_SLOT.items():
        if word in phrase:
            return slot
    return ""


def _sub_times(t: str) -> str:
    def mk(h: int, m: int, ampm: str | None) -> str:
        ampm = (ampm or "").replace(".", "")[:1]  # a / p / ""
        return f" __t{h}:{m:02d}:{ampm}__ "

    t = _RE_TIME_COLON.sub(lambda m: mk(int(m.group(1)), int(m.group(2)), m.group(3)), t)
    t = _RE_TIME_AMPM.sub(lambda m: mk(int(m.group(1)), 0, m.group(2)), t)
    t = _RE_TIME_BAJE.sub(lambda m: mk(int(m.group(1)), 0, None), t)
    t = _RE_TIME_WORD.sub(lambda m: " " + mk(HINDI_NUMBERS[m.group(1)], 0, None), t)
    return t


def _to_24h(hour: int, minute: int, ampm: str, slot: str | None) -> str | None:
    if not (0 <= hour <= 24 and 0 <= minute < 60):
        return None
    if ampm == "a":
        hour = 0 if hour == 12 else hour
    elif ampm == "p":
        hour = hour if hour == 12 else hour + 12
    elif hour <= 12:
        if slot == "shaam" and hour < 12:
            hour += 12
        elif slot == "raat":
            if 6 <= hour <= 11:
                hour += 12
            elif hour == 12:
                hour = 0
        elif slot == "dopahar":
            if 1 <= hour <= 6:
                hour += 12
        elif slot == "subah":
            hour = 0 if hour == 12 else hour
        elif slot is None:
            if 1 <= hour <= 4:
                hour += 12
    if hour >= 24:
        return None
    return f"{hour:02d}:{minute:02d}"


def slot_for_time(hhmm: str) -> str:
    h = int(hhmm.split(":")[0])
    if 4 <= h < 12:
        return "subah"
    if 12 <= h < 16:
        return "dopahar"
    if 16 <= h < 20:
        return "shaam"
    return "raat"


def _clean_name(tokens: list[str]) -> str:
    name = " ".join(tokens).strip()
    if not name:
        return ""
    if name.isascii() and name.replace(" ", "").isalpha() and len(name) <= 3:
        return name.upper()
    return name[:1].upper() + name[1:] if name.isascii() else name


def _display_medicine(name: str, kind: str) -> str:
    kind_roman = KIND_TO_ROMAN.get(kind, kind)
    if not name:
        return kind_roman.capitalize()
    if kind_roman in ("goli", "dawai"):
        return f"{name} ki {kind_roman}"
    return f"{name} {kind_roman}"


def _parse_clause(tokens: list[str]) -> dict:
    slots: list[str] = []
    times: list[tuple[int, int, str]] = []
    food = "any"
    kind_idx = None
    for i, tok in enumerate(tokens):
        if tok in TOKEN_TO_SLOT:
            s = TOKEN_TO_SLOT[tok]
            if s not in slots:
                slots.append(s)
        elif tok.startswith("__t") and tok.endswith("__"):
            h, m, ap = tok[3:-2].split(":")
            times.append((int(h), int(m), ap))
        elif tok == "__fbefore__":
            food = "before"
        elif tok == "__fafter__":
            food = "after"
        elif kind_idx is None and tok in KIND_TO_ROMAN:
            kind_idx = i

    medicine = None
    if kind_idx is not None:
        j = kind_idx - 1
        if j >= 0 and tokens[j] in ("ki", "ka", "ke", "की", "का", "के"):
            j -= 1
        name_tokens: list[str] = []
        while j >= 0 and len(name_tokens) < 3:
            tok = tokens[j]
            if tok in STOP_WORDS or tok.startswith("__"):
                break
            name_tokens.insert(0, tok)
            j -= 1
        medicine = _display_medicine(_clean_name(name_tokens), tokens[kind_idx])

    return {"slots": slots, "times": times, "food": food, "medicine": medicine}


def _clauses(text: str) -> list[list[str]]:
    t = _normalize(text)
    t = _sub_food(t)
    t = _sub_times(t)
    t = re.sub(r"[,;\n]", " | ", t)
    t = re.sub(r"\.(?=\s|$)", " | ", t)
    clauses: list[list[str]] = [[]]
    for tok in t.split():
        if tok == "|" or tok in CONNECTORS:
            if clauses[-1]:
                clauses.append([])
        else:
            clauses[-1].append(tok)
    return [c for c in clauses if c]


def _build_items(medicine: str, slots: list[str], times: list[tuple[int, int, str]], food: str) -> list[dict]:
    pairs: list[tuple[str, str, bool]] = []  # (slot, hhmm, guessed)
    if times and len(times) == len(slots):
        for s, (h, m, ap) in zip(slots, times):
            hhmm = _to_24h(h, m, ap, s)
            pairs.append((s, hhmm, False) if hhmm else (s, DEFAULT_TIMES[s], True))
    elif times and not slots:
        for (h, m, ap) in times:
            hhmm = _to_24h(h, m, ap, None)
            if hhmm:
                pairs.append((slot_for_time(hhmm), hhmm, False))
    elif times and len(slots) == 1:
        h, m, ap = times[0]
        hhmm = _to_24h(h, m, ap, slots[0])
        pairs.append((slots[0], hhmm, False) if hhmm else (slots[0], DEFAULT_TIMES[slots[0]], True))
    elif slots:
        pairs = [(s, DEFAULT_TIMES[s], False) for s in slots]
    else:
        pairs = [("subah", DEFAULT_TIMES["subah"], True)]
    return [
        {"medicine": medicine, "slot": s, "time": hhmm, "food": food, "guessed": guessed}
        for s, hhmm, guessed in pairs
    ]


def parse_schedule(text: str) -> list[dict]:
    items: list[dict] = []
    carry_slots: list[str] = []
    carry_times: list[tuple[int, int, str]] = []
    carry_food = "any"
    last_med: dict | None = None

    for tokens in _clauses(text):
        c = _parse_clause(tokens)
        if c["medicine"]:
            slots = list(dict.fromkeys(carry_slots + c["slots"]))
            times = carry_times + c["times"]
            food = c["food"] if c["food"] != "any" else carry_food
            items += _build_items(c["medicine"], slots, times, food)
            last_med = {"medicine": c["medicine"], "food": food}
            carry_slots, carry_times, carry_food = [], [], "any"
        elif c["slots"] or c["times"]:
            carry_slots += c["slots"]
            carry_times += c["times"]
            if c["food"] != "any":
                carry_food = c["food"]

    if (carry_slots or carry_times) and last_med:
        items += _build_items(last_med["medicine"], carry_slots, carry_times, last_med["food"])

    seen: set[tuple[str, str]] = set()
    unique = []
    for it in items:
        key = (it["medicine"].lower(), it["time"])
        if key not in seen:
            seen.add(key)
            unique.append(it)
    unique.sort(key=lambda x: x["time"])
    return unique


# ---------- spoken / written read-back ----------

FOOD_PHRASE = {"before": "khaane se pehle", "after": "khaane ke baad", "any": ""}
SLOT_LABEL = {"subah": "Subah", "dopahar": "Dopahar", "shaam": "Shaam", "raat": "Raat"}


def format_time(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    h12 = h % 12 or 12
    return f"{h12} baje" if m == 0 else f"{h12}:{m:02d} baje"


def readback(items: list[dict], parent_label: str = "Papa") -> str:
    if not items:
        return (
            "Mujhe koi dawai samajh nahi aayi. Kripya dobara boliye, jaise: "
            "subah BP ki goli khaane ke baad, raat ko sugar ki goli."
        )
    parts = []
    for it in items:
        piece = f"{SLOT_LABEL.get(it['slot'], it['slot'])} {format_time(it['time'])}, {it['medicine']}"
        food = FOOD_PHRASE.get(it.get("food", "any"), "")
        if food:
            piece += f", {food}"
        parts.append(piece)
    return f"{parent_label} ke liye: " + ". ".join(parts) + ". Kya yeh sahi hai?"
