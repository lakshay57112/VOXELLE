"""Core logic: dose events, reminders, replies, missed-dose alerts.

Safety rule baked in here: the app only reminds and records. It never says what to take,
how much, or answers a health question. Symptoms and confusion are passed to the family.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from datetime import time as dtime

from . import config
from .db import db, get_setting, now_iso
from .parser import FOOD_PHRASE, format_time
from .replies import Reply, classify_reply

Note = tuple[str, str, str, str, str]  # (role, title, body, url, tag)

STALE_AFTER = timedelta(hours=6)


# ---------- text builders ----------

def _food_suffix(food: str) -> str:
    phrase = FOOD_PHRASE.get(food, "")
    return f", {phrase}" if phrase else ""


def reminder_body(ev: sqlite3.Row, parent: str) -> str:
    return f"{parent}, {ev['slot']} ki {ev['medicine']} lene ka time ho gaya{_food_suffix(ev['food'])}."


def reminder_say(ev: sqlite3.Row, parent: str) -> str:
    return (
        f"{parent}, {ev['slot']} ki dawai ka time ho gaya hai. "
        f"{ev['medicine']} lijiye{_food_suffix(ev['food'])}. Le li kya?"
    )


def event_dict(ev: sqlite3.Row, parent: str) -> dict:
    return {
        "id": ev["id"],
        "medicine": ev["medicine"],
        "slot": ev["slot"],
        "food": ev["food"],
        "due_date": ev["due_date"],
        "due_time": ev["due_time"][:5],
        "status": ev["status"],
        "remind_count": ev["remind_count"],
        "last_reply": ev["last_reply"],
        "body": reminder_body(ev, parent),
        "say": reminder_say(ev, parent),
    }


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _add_alert(con: sqlite3.Connection, kind: str, message: str, event_id: int | None, now: datetime) -> None:
    con.execute(
        "INSERT INTO alerts(kind, message, event_id, created_at) VALUES(?,?,?,?)",
        (kind, message, event_id, now_iso(now)),
    )


# ---------- scheduler tick ----------

def tick(now: datetime | None = None) -> list[Note]:
    """Create due events, re-remind, wake snoozed ones, and flag missed doses."""
    now = now or datetime.now(config.TZ)
    notes: list[Note] = []
    with db() as con:
        parent = get_setting(con, "parent_label", "Papa")

        # 1. start an event for every schedule item whose time has come
        for it in con.execute("SELECT * FROM schedule_items WHERE active=1").fetchall():
            due = datetime.combine(now.date(), dtime.fromisoformat(it["time"]), tzinfo=config.TZ)
            age = (now - due).total_seconds()
            if not (0 <= age <= config.DUE_WINDOW_MIN * 60):
                continue
            cur = con.execute(
                "INSERT OR IGNORE INTO dose_events(item_id, medicine, slot, food, due_date, due_time, status, "
                "remind_count, last_reminded_at, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (it["id"], it["medicine"], it["slot"], it["food"], now.date().isoformat(), it["time"],
                 "due", 1, now_iso(now), now_iso(now)),
            )
            if cur.rowcount:
                ev = con.execute("SELECT * FROM dose_events WHERE id=?", (cur.lastrowid,)).fetchone()
                notes.append(("parent", "Dawai ka time 💊", reminder_body(ev, parent), "/parent", f"dose-{ev['id']}"))

        # 2. move open events forward
        for ev in con.execute("SELECT * FROM dose_events WHERE status IN ('due','snoozed')").fetchall():
            created = _parse_dt(ev["created_at"])
            missed_after = ev["missed_after_sec"] or config.MISSED_AFTER_MIN * 60
            elapsed = (now - created).total_seconds()

            if now - created > STALE_AFTER:  # leftover from a long outage: close it quietly
                con.execute("UPDATE dose_events SET status='missed' WHERE id=?", (ev["id"],))
                continue

            if elapsed >= missed_after:
                con.execute("UPDATE dose_events SET status='missed' WHERE id=?", (ev["id"],))
                msg = (
                    f"{parent} ne {ev['slot']} ki {ev['medicine']} abhi tak nahi li "
                    f"({format_time(ev['due_time'][:5])} ki dawai)."
                )
                _add_alert(con, "missed", msg, ev["id"], now)
                notes.append(("family", "Dawai chhoot gayi ⚠️", msg, "/family", f"missed-{ev['id']}"))
                continue

            if ev["status"] == "snoozed":
                until = _parse_dt(ev["snooze_until"])
                if until and now >= until:
                    con.execute(
                        "UPDATE dose_events SET status='due', remind_count=remind_count+1, last_reminded_at=? WHERE id=?",
                        (now_iso(now), ev["id"]),
                    )
                    ev = con.execute("SELECT * FROM dose_events WHERE id=?", (ev["id"],)).fetchone()
                    notes.append(("parent", "Dawai ka time 💊", reminder_body(ev, parent), "/parent", f"dose-{ev['id']}"))
                continue

            # status == due: nudge again if they haven't answered
            every = config.REMIND_EVERY_MIN * 60
            if ev["missed_after_sec"]:
                every = min(every, max(20, ev["missed_after_sec"] // 3))
            last = _parse_dt(ev["last_reminded_at"]) or created
            if ev["remind_count"] < config.MAX_REMINDERS and (now - last).total_seconds() >= every:
                con.execute(
                    "UPDATE dose_events SET remind_count=remind_count+1, last_reminded_at=? WHERE id=?",
                    (now_iso(now), ev["id"]),
                )
                ev = con.execute("SELECT * FROM dose_events WHERE id=?", (ev["id"],)).fetchone()
                notes.append(("parent", "Dawai ka time 💊", reminder_body(ev, parent), "/parent", f"dose-{ev['id']}"))
    return notes


# ---------- parent replies ----------

def handle_reply(
    event_id: int,
    text: str | None = None,
    action: str | None = None,
    minutes: int | None = None,
    now: datetime | None = None,
) -> tuple[dict, list[Note]]:
    now = now or datetime.now(config.TZ)
    notes: list[Note] = []
    with db() as con:
        parent = get_setting(con, "parent_label", "Papa")
        ev = con.execute("SELECT * FROM dose_events WHERE id=?", (event_id,)).fetchone()
        if not ev or ev["status"] not in ("due", "snoozed"):
            return {"outcome": "stale", "say": "Yeh yaad dilana ab khatam ho chuka hai."}, notes

        if action == "taken":
            reply = Reply("taken")
        elif action == "snooze":
            reply = Reply("snooze", max(2, min(60, minutes or 10)))
        else:
            reply = classify_reply(text or "")

        said = (text or "").strip()[:200] or None
        outcome = reply.outcome

        if outcome == "taken":
            con.execute(
                "UPDATE dose_events SET status='taken', responded_at=?, last_reply=? WHERE id=?",
                (now_iso(now), said or "(button)", event_id),
            )
            say = f"Bahut accha {parent}. Maine likh liya ki aapne dawai le li."

        elif outcome == "snooze":
            until = now + timedelta(minutes=reply.snooze_min)
            con.execute(
                "UPDATE dose_events SET status='snoozed', snooze_until=?, last_reply=? WHERE id=?",
                (now_iso(until), said or "(button)", event_id),
            )
            say = f"Theek hai, {reply.snooze_min} minute baad phir se yaad dila denge."

        elif outcome in ("symptom", "confused"):
            con.execute(
                "UPDATE dose_events SET status='escalated', responded_at=?, last_reply=? WHERE id=?",
                (now_iso(now), said, event_id),
            )
            quote = f' Unhone kaha: "{said}".' if said else ""
            if outcome == "symptom":
                msg = (
                    f"{parent} ne {ev['slot']} ki {ev['medicine']} ke samay apni sehat ke baare mein kuch kaha.{quote} "
                    "Kripya turant unse baat karein ya doctor se sampark karein."
                )
                title = "Turant dhyan dein 🚨"
                say = (
                    "Main dawai ya sehat ke baare mein salah nahi de sakte. "
                    "Humne aapke parivaar ko khabar kar di hai. Kripya doctor se baat karein."
                )
            else:
                msg = (
                    f"{parent} ko {ev['slot']} ki {ev['medicine']} ke baare mein ulajhan lag rahi hai.{quote} "
                    "Kripya unse baat karke madad karein."
                )
                title = "Madad chahiye"
                say = "Koi baat nahi. Humne parivaar ko bata diya hai, woh aapse sampark karenge."
            _add_alert(con, outcome, msg, event_id, now)
            notes.append(("family", title, msg, "/family", f"escalated-{event_id}"))

        else:  # unknown: never guess, ask again
            con.execute("UPDATE dose_events SET last_reply=? WHERE id=?", (said, event_id))
            say = "Samajh nahi aaya. Kripya 'haan' ya 'baad mein' boliye, ya neeche ka button dabaiye."

    return {"outcome": outcome, "say": say, "snooze_min": reply.snooze_min if outcome == "snooze" else None}, notes


# ---------- views for the UI ----------

def pending_event(now: datetime | None = None) -> dict | None:
    with db() as con:
        parent = get_setting(con, "parent_label", "Papa")
        ev = con.execute(
            "SELECT * FROM dose_events WHERE status='due' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return event_dict(ev, parent) if ev else None


def next_dose(now: datetime | None = None) -> dict | None:
    now = now or datetime.now(config.TZ)
    best = None
    with db() as con:
        for it in con.execute("SELECT * FROM schedule_items WHERE active=1").fetchall():
            due = datetime.combine(now.date(), dtime.fromisoformat(it["time"]), tzinfo=config.TZ)
            day = "aaj"
            if due <= now:
                due += timedelta(days=1)
                day = "kal"
            if best is None or due < best[0]:
                best = (due, day, it)
    if not best:
        return None
    due, day, it = best
    return {
        "day": day,
        "time": it["time"],
        "slot": it["slot"],
        "medicine": it["medicine"],
        "food": it["food"],
    }


def fire_demo(item_id: int | None = None, missed_after_sec: int = 90, now: datetime | None = None) -> tuple[int, list[Note]]:
    """Start a reminder right now, with a short missed-dose timer, for demos and testing."""
    now = now or datetime.now(config.TZ)
    with db() as con:
        parent = get_setting(con, "parent_label", "Papa")
        it = None
        if item_id:
            it = con.execute("SELECT * FROM schedule_items WHERE id=?", (item_id,)).fetchone()
        if it is None:
            it = con.execute("SELECT * FROM schedule_items WHERE active=1 ORDER BY time LIMIT 1").fetchone()
        medicine = it["medicine"] if it else "BP ki goli"
        slot = it["slot"] if it else "subah"
        food = it["food"] if it else "after"
        cur = con.execute(
            "INSERT INTO dose_events(item_id, medicine, slot, food, due_date, due_time, status, remind_count, "
            "last_reminded_at, missed_after_sec, is_demo, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (it["id"] if it else None, medicine, slot, food, now.date().isoformat(), now.strftime("%H:%M:%S"),
             "due", 1, now_iso(now), max(30, missed_after_sec), 1, now_iso(now)),
        )
        ev = con.execute("SELECT * FROM dose_events WHERE id=?", (cur.lastrowid,)).fetchone()
        note: Note = ("parent", "Dawai ka time 💊", reminder_body(ev, parent), "/parent", f"dose-{ev['id']}")
        return ev["id"], [note]


def get_log(limit: int = 60) -> list[dict]:
    with db() as con:
        rows = con.execute("SELECT * FROM dose_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [
            {
                "id": r["id"],
                "date": r["due_date"],
                "time": r["due_time"][:5],
                "slot": r["slot"],
                "medicine": r["medicine"],
                "status": r["status"],
                "responded_at": r["responded_at"],
                "last_reply": r["last_reply"],
                "is_demo": bool(r["is_demo"]),
            }
            for r in rows
        ]
