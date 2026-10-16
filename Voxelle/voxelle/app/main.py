from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, gnani, push, scheduler, service
from .db import db, get_setting, init_db, now_iso, set_setting
from .parser import SLOT_LABEL, parse_schedule, readback

VALID_SLOTS = set(SLOT_LABEL)
VALID_FOOD = {"before", "after", "any"}
_RE_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(scheduler.run_forever())
    yield
    task.cancel()


app = FastAPI(title="Voxelle", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# ---------- pages ----------

def _page(name: str) -> FileResponse:
    return FileResponse(config.STATIC_DIR / name, headers={"Cache-Control": "no-cache"})


@app.get("/")
def home():
    return _page("index.html")


@app.get("/parent")
def parent_page():
    return _page("parent.html")


@app.get("/family")
def family_page():
    return _page("family.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        config.STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/manifest.webmanifest")
def manifest(role: str = "parent"):
    role = role if role in ("parent", "family") else "parent"
    return JSONResponse(
        {
            "name": "Voxelle",
            "short_name": "Voxelle",
            "description": "Voice medicine reminders for parents",
            "start_url": f"/{role}",
            "scope": "/",
            "display": "standalone",
            "background_color": "#fbf6e9",
            "theme_color": "#2f6b3f",
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        },
        media_type="application/manifest+json",
    )


# ---------- config / settings ----------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    with db() as con:
        parent = get_setting(con, "parent_label", "Papa")
    return {
        "vapid_public_key": config.VAPID_PUBLIC_KEY,
        "push_ready": push.push_ready(),
        "voice_ready": bool(config.GNANI_API_KEY),
        "parent_label": parent,
    }


class SettingsIn(BaseModel):
    parent_label: str


@app.post("/api/settings")
def save_settings(body: SettingsIn):
    label = body.parent_label.strip()[:30] or "Papa"
    with db() as con:
        set_setting(con, "parent_label", label)
    return {"parent_label": label}


# ---------- voice (Prisma / Timbre) ----------

@app.post("/api/stt")
async def stt(audio: UploadFile = File(...)):
    data = await audio.read()
    if len(data) < 800:
        return JSONResponse({"error": "audio_too_short"}, status_code=400)
    try:
        text = await asyncio.to_thread(gnani.transcribe, data, audio.filename or "audio.wav")
    except gnani.GnaniError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status if e.status in (400, 403, 429, 503) else 502)
    return {"transcript": text}


class TtsIn(BaseModel):
    text: str


@app.post("/api/tts")
async def tts(body: TtsIn):
    text = body.text.strip()[:500]
    if not text:
        return JSONResponse({"error": "empty_text"}, status_code=400)
    try:
        audio = await asyncio.to_thread(gnani.synthesize, text)
    except gnani.GnaniError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status if e.status in (400, 403, 429, 503) else 502)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


# ---------- schedule (family side) ----------

class ParseIn(BaseModel):
    text: str


@app.post("/api/schedule/parse")
def schedule_parse(body: ParseIn):
    items = parse_schedule(body.text)
    with db() as con:
        parent = get_setting(con, "parent_label", "Papa")
    return {"items": items, "readback": readback(items, parent), "heard": body.text}


class ItemIn(BaseModel):
    medicine: str
    time: str
    slot: str = "subah"
    food: str = "any"


class ConfirmIn(BaseModel):
    items: list[ItemIn]
    replace: bool = True


@app.post("/api/schedule/confirm")
def schedule_confirm(body: ConfirmIn):
    clean = []
    for it in body.items:
        med = it.medicine.strip()[:60]
        if not med or not _RE_HHMM.match(it.time):
            return JSONResponse({"error": "bad_item"}, status_code=400)
        clean.append((med, it.time, it.slot if it.slot in VALID_SLOTS else "subah", it.food if it.food in VALID_FOOD else "any"))
    if not clean:
        return JSONResponse({"error": "empty_schedule"}, status_code=400)
    with db() as con:
        if body.replace:
            con.execute("UPDATE schedule_items SET active=0 WHERE active=1")
        for med, hhmm, slot, food in clean:
            con.execute(
                "INSERT INTO schedule_items(medicine, time, slot, food, created_at) VALUES(?,?,?,?,?)",
                (med, hhmm, slot, food, now_iso()),
            )
    return {"saved": len(clean)}


@app.get("/api/schedule")
def schedule_list():
    with db() as con:
        rows = con.execute("SELECT * FROM schedule_items WHERE active=1 ORDER BY time").fetchall()
    return {"items": [dict(r) for r in rows]}


@app.delete("/api/schedule/{item_id}")
def schedule_delete(item_id: int):
    with db() as con:
        con.execute("UPDATE schedule_items SET active=0 WHERE id=?", (item_id,))
    return {"ok": True}


# ---------- parent side ----------

@app.get("/api/parent/state")
def parent_state():
    with db() as con:
        parent = get_setting(con, "parent_label", "Papa")
    return {"parent_label": parent, "event": service.pending_event(), "next": service.next_dose()}


class ReplyIn(BaseModel):
    event_id: int
    text: str | None = None
    action: str | None = None  # taken | snooze
    minutes: int | None = None


@app.post("/api/parent/reply")
async def parent_reply(body: ReplyIn):
    result, notes = await asyncio.to_thread(
        service.handle_reply, body.event_id, body.text, body.action, body.minutes
    )
    if notes:
        asyncio.create_task(scheduler.dispatch(notes))
    return result


# ---------- push subscriptions ----------

class SubIn(BaseModel):
    role: str
    subscription: dict


@app.post("/api/push/subscribe")
def push_subscribe(body: SubIn):
    if body.role not in ("parent", "family") or "endpoint" not in body.subscription:
        return JSONResponse({"error": "bad_subscription"}, status_code=400)
    push.save_subscription(body.role, body.subscription)
    return {"ok": True}


@app.post("/api/push/test")
async def push_test(role: str = "parent"):
    sent = await asyncio.to_thread(
        push.send, role, "Test notification", "Yeh ek test hai. Dawai ka time 💊", f"/{role}", "test"
    )
    return {"sent": sent, "push_ready": push.push_ready()}


# ---------- family: log, alerts, demo ----------

@app.get("/api/log")
def log_list():
    return {"events": service.get_log()}


@app.get("/api/alerts")
def alerts_list():
    with db() as con:
        rows = con.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 30").fetchall()
    return {"alerts": [dict(r) for r in rows]}


@app.post("/api/alerts/seen")
def alerts_seen():
    with db() as con:
        con.execute("UPDATE alerts SET seen=1 WHERE seen=0")
    return {"ok": True}


class DemoIn(BaseModel):
    item_id: int | None = None
    missed_after_sec: int = 90


@app.post("/api/demo/fire")
async def demo_fire(body: DemoIn):
    event_id, notes = await asyncio.to_thread(service.fire_demo, body.item_id, body.missed_after_sec)
    asyncio.create_task(scheduler.dispatch(notes))
    return {"event_id": event_id, "missed_after_sec": max(30, body.missed_after_sec)}
