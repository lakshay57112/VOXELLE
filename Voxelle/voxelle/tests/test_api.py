from fastapi.testclient import TestClient

from app.main import app


def test_full_family_flow_through_api():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"ok": True}
        cfg = client.get("/api/config").json()
        assert cfg["voice_ready"] is False and cfg["parent_label"] == "Papa"

        client.post("/api/settings", json={"parent_label": "Mummy"})
        parsed = client.post(
            "/api/schedule/parse",
            json={"text": "subah BP ki goli khaane ke baad, raat ko sugar ki goli"},
        ).json()
        assert len(parsed["items"]) == 2
        assert parsed["readback"].startswith("Mummy ke liye:")

        # nothing is scheduled until the family confirms
        assert client.get("/api/schedule").json()["items"] == []
        assert client.post("/api/schedule/confirm", json={"items": parsed["items"]}).json() == {"saved": 2}
        items = client.get("/api/schedule").json()["items"]
        assert [i["time"] for i in items] == ["08:00", "21:00"]

        fired = client.post("/api/demo/fire", json={"missed_after_sec": 60}).json()
        state = client.get("/api/parent/state").json()
        assert state["event"]["id"] == fired["event_id"]
        assert state["event"]["say"].startswith("Mummy,")

        reply = client.post("/api/parent/reply", json={"event_id": fired["event_id"], "text": "haan kha li"}).json()
        assert reply["outcome"] == "taken"
        log = client.get("/api/log").json()["events"]
        assert log[0]["status"] == "taken"


def test_voice_endpoints_degrade_cleanly_without_key():
    with TestClient(app) as client:
        r = client.post("/api/tts", json={"text": "namaste"})
        assert r.status_code == 503 and r.json()["error"] == "no_api_key"
        r = client.post("/api/stt", files={"audio": ("a.wav", b"0" * 2000, "audio/wav")})
        assert r.status_code == 503


def test_bad_confirm_is_rejected():
    with TestClient(app) as client:
        r = client.post("/api/schedule/confirm", json={"items": [{"medicine": "x", "time": "25:99"}]})
        assert r.status_code == 400
        r = client.post("/api/schedule/confirm", json={"items": []})
        assert r.status_code == 400
