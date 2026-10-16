import pytest

from app.replies import classify_reply


@pytest.mark.parametrize(
    "text",
    ["haan, kha li", "Haan le li", "ho gaya", "हाँ खा ली", "yes", "kha liya maine", "khali"],
)
def test_taken(text):
    assert classify_reply(text).outcome == "taken"


@pytest.mark.parametrize(
    "text,minutes",
    [("abhi nahi, 10 minute baad", 10), ("thodi der baad", 10), ("5 minute ruko", 5),
     ("बाद में", 10), ("aadha ghanta baad mein", 30), ("nahi", 10), ("paanch minute baad", 5)],
)
def test_snooze(text, minutes):
    r = classify_reply(text)
    assert r.outcome == "snooze" and r.snooze_min == minutes


@pytest.mark.parametrize(
    "text",
    ["mujhe chakkar aa raha hai", "seene mein dard hai", "ghabrahat ho rahi hai", "tabiyat kharab hai", "चक्कर आ रहा है"],
)
def test_symptom_is_escalated_not_answered(text):
    assert classify_reply(text).outcome == "symptom"


@pytest.mark.parametrize("text", ["kaun si goli leni hai", "kitni goli lun", "yaad nahi kya lena hai"])
def test_confused(text):
    assert classify_reply(text).outcome == "confused"


def test_symptom_beats_taken():
    assert classify_reply("haan le li par chakkar aa raha hai").outcome == "symptom"


@pytest.mark.parametrize("text", ["", "   ", "mausam accha hai"])
def test_unknown(text):
    assert classify_reply(text).outcome == "unknown"


def test_khali_pet_is_not_taken():
    assert classify_reply("khali pet").outcome == "unknown"
