"""Web push notifications (the 'time to take your medicine' pop-up on the phone)."""
from __future__ import annotations

import json
import logging

from . import config
from .db import db

log = logging.getLogger("voxelle.push")

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover
    webpush = None
    WebPushException = Exception


def push_ready() -> bool:
    return bool(webpush and config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY_FILE.exists())


def save_subscription(role: str, subscription: dict) -> None:
    from .db import now_iso

    endpoint = subscription["endpoint"]
    with db() as con:
        con.execute(
            "INSERT INTO push_subs(role, endpoint, sub_json, created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(endpoint) DO UPDATE SET role=excluded.role, sub_json=excluded.sub_json",
            (role, endpoint, json.dumps(subscription), now_iso()),
        )


def send(role: str, title: str, body: str, url: str = "/", tag: str = "voxelle") -> int:
    """Send a push to every device registered for this role. Returns how many were delivered."""
    if not push_ready():
        return 0
    with db() as con:
        subs = con.execute("SELECT endpoint, sub_json FROM push_subs WHERE role=?", (role,)).fetchall()
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    sent = 0
    for row in subs:
        try:
            webpush(
                subscription_info=json.loads(row["sub_json"]),
                data=payload,
                vapid_private_key=str(config.VAPID_PRIVATE_KEY_FILE),
                vapid_claims={"sub": config.VAPID_SUBJECT},
                ttl=3600,
            )
            sent += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):  # subscription expired
                with db() as con:
                    con.execute("DELETE FROM push_subs WHERE endpoint=?", (row["endpoint"],))
            else:
                log.warning("push failed (%s): %s", status, e)
        except Exception as e:  # network etc. must never crash the scheduler
            log.warning("push error: %s", e)
    return sent
