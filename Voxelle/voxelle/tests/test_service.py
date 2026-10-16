from datetime import datetime, timedelta

from app import config, service
from app.db import db, now_iso


def add_item(medicine="BP ki goli", hhmm="08:00", slot="subah", food="after"):
    with db() as con:
        con.execute(
            "INSERT INTO schedule_items(medicine, time, slot, food, created_at) VALUES(?,?,?,?,?)",
            (medicine, hhmm, slot, food, now_iso()),
        )


def at(hhmm, day=(2026, 10, 17), sec=0):
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(*day, h, m, sec, tzinfo=config.TZ)


def status_of(event_id):
    with db() as con:
        return con.execute("SELECT status FROM dose_events WHERE id=?", (event_id,)).fetchone()["status"]


def test_no_event_before_due_time():
    add_item()
    assert service.tick(at("07:59")) == []


def test_event_created_once_and_parent_notified():
    add_item()
    notes = service.tick(at("08:00", sec=5))
    assert len(notes) == 1 and notes[0][0] == "parent"
    assert "BP ki goli" in notes[0][2] and "khaane ke baad" in notes[0][2]
    assert service.tick(at("08:00", sec=30)) == []  # no duplicate
    ev = service.pending_event()
    assert ev and ev["medicine"] == "BP ki goli"


def test_taken_reply_logs_dose_and_no_missed_alert():
    add_item()
    service.tick(at("08:00", sec=1))
    ev = service.pending_event()
    result, notes = service.handle_reply(ev["id"], text="haan, kha li", now=at("08:02"))
    assert result["outcome"] == "taken" and notes == []
    assert status_of(ev["id"]) == "taken"
    assert service.tick(at("09:00")) == []  # nothing missed
    with db() as con:
        assert con.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"] == 0


def test_missed_dose_alerts_family():
    add_item()
    service.tick(at("08:00", sec=1))
    notes = service.tick(at("08:00") + timedelta(minutes=config.MISSED_AFTER_MIN, seconds=5))
    family = [n for n in notes if n[0] == "family"]
    assert len(family) == 1 and "nahi li" in family[0][2]
    with db() as con:
        assert con.execute("SELECT kind FROM alerts").fetchone()["kind"] == "missed"
    assert service.pending_event() is None


def test_re_reminds_then_stops_at_max():
    add_item()
    base = at("08:00", sec=1)
    service.tick(base)
    sent = 0
    for i in range(1, 6):
        notes = service.tick(base + timedelta(minutes=config.REMIND_EVERY_MIN * i, seconds=1))
        sent += len([n for n in notes if n[0] == "parent"])
        if i * config.REMIND_EVERY_MIN >= config.MISSED_AFTER_MIN:
            break
    assert sent <= config.MAX_REMINDERS


def test_snooze_wakes_up_again():
    add_item()
    service.tick(at("08:00", sec=1))
    ev = service.pending_event()
    result, _ = service.handle_reply(ev["id"], text="10 minute baad", now=at("08:01"))
    assert result["outcome"] == "snooze" and result["snooze_min"] == 10
    assert service.pending_event() is None
    assert service.tick(at("08:05")) == []
    notes = service.tick(at("08:11"))
    assert [n[0] for n in notes] == ["parent"]
    assert service.pending_event() is not None


def test_symptom_is_escalated_and_never_answered_medically():
    add_item()
    service.tick(at("08:00", sec=1))
    ev = service.pending_event()
    result, notes = service.handle_reply(ev["id"], text="mujhe chakkar aa raha hai", now=at("08:02"))
    assert result["outcome"] == "symptom"
    assert "doctor" in result["say"].lower() and "salah nahi" in result["say"]
    assert notes and notes[0][0] == "family" and "chakkar" in notes[0][2]
    assert status_of(ev["id"]) == "escalated"
    # no extra "missed" alert for an escalated dose
    later = service.tick(at("08:00") + timedelta(minutes=45))
    assert [n for n in later if n[0] == "family"] == []


def test_unknown_reply_asks_again_without_changing_state():
    add_item()
    service.tick(at("08:00", sec=1))
    ev = service.pending_event()
    result, notes = service.handle_reply(ev["id"], text="mausam accha hai", now=at("08:02"))
    assert result["outcome"] == "unknown" and notes == []
    assert status_of(ev["id"]) == "due"


def test_button_actions():
    add_item()
    service.tick(at("08:00", sec=1))
    ev = service.pending_event()
    result, _ = service.handle_reply(ev["id"], action="taken", now=at("08:02"))
    assert result["outcome"] == "taken"
    again, _ = service.handle_reply(ev["id"], action="taken", now=at("08:03"))
    assert again["outcome"] == "stale"


def test_late_start_does_not_fire_ancient_doses():
    add_item(hhmm="06:00", slot="subah")
    assert service.tick(at("15:00")) == []


def test_next_dose():
    add_item("BP ki goli", "08:00", "subah")
    add_item("Sugar ki goli", "21:00", "raat", "any")
    nxt = service.next_dose(at("10:00"))
    assert nxt["medicine"] == "Sugar ki goli" and nxt["day"] == "aaj"
    nxt = service.next_dose(at("22:00"))
    assert nxt["medicine"] == "BP ki goli" and nxt["day"] == "kal"


def test_demo_fire_missed_timer():
    add_item()
    now = at("12:00")
    eid, notes = service.fire_demo(missed_after_sec=60, now=now)
    assert notes[0][0] == "parent"
    out = service.tick(now + timedelta(seconds=61))
    assert any(n[0] == "family" for n in out)
    assert status_of(eid) == "missed"
