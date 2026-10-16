# Voxelle

A voice-first medicine reminder for parents, in Hindi and Hinglish.

The family says the schedule out loud ("Papa ko subah BP ki goli khaane ke baad, raat ko sugar ki goli"). The app reads it back, the family confirms, and from then on it reminds the parent at dose time with a phone notification and a spoken message. It listens for the answer ("haan, kha li" / "10 minute baad"), logs the dose, and tells the family if a dose is missed.

Built for the Great Indian AI Internship Challenge with Gnani's **Prisma** (speech to text) and **Timbre** (text to speech).

## What it does

- **Setup by voice.** Speak or type the schedule. Simple rules (no LLM) turn it into medicine, time and before/after food. Hindi, Hinglish, English and Devanagari work.
- **Read-back before anything starts.** The schedule is spoken and shown back. Nothing is saved until the family taps "Sahi hai".
- **Reminder.** At dose time the parent's phone gets a notification ("Papa, subah ki BP ki goli lene ka time ho gaya"). Open the page and it speaks the reminder, then listens.
- **Replies.** "haan le li" logs the dose. "10 minute baad" snoozes and asks again. Anything else is asked again, never guessed.
- **Family alerts.** A missed dose (no answer for 30 min by default) sends the family a notification and shows in their log.
- **Dose log.** Taken, snoozed, missed, escalated, with what the parent said.

## Safety rules (built into the code, say them in the demo)

1. It only reminds and records. It never says what to take, how much, or answers a health question.
2. The family confirms the schedule before it starts.
3. If the parent mentions a symptom ("chakkar", "dard", "ghabrahat") or sounds confused about which medicine to take, the app does not answer. It tells them to talk to a doctor and alerts the family straight away.
4. Use a made-up schedule and people who agreed to be in the demo. No real medical records.

## Run it

```bash
cd voxelle
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then put your key in GNANI_API_KEY
python scripts/gen_vapid.py   # one-time: creates the keys phone notifications need
                              # then set VAPID_SUBJECT in .env to your own email

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

- `/family` is for the son or daughter: set the schedule, see the log and alerts.
- `/parent` is for the parent: big buttons, voice reminders.

Without a Gnani key everything still works: you type the schedule, and the browser's own voice reads it out. Add the key to get Prisma and Timbre.

### On a real phone (needed for your demo)

Phones only allow the microphone and notifications over **HTTPS**, so `localhost` is not enough. Easiest way:

```bash
cloudflared tunnel --url http://localhost:8000     # or: ngrok http 8000
```

Open the `https://...` address it prints on both phones.

- **Android (Chrome):** works straight away. Tap "Shuru karein" on the parent page and allow notifications and the mic.
- **iPhone:** notifications only work after Share, then "Add to Home Screen", then opening the app from the home screen.

### Day 1: test the voices first

```bash
python scripts/test_voice.py stt recording.wav          # what does Prisma hear?
python scripts/test_voice.py batch recordings/          # a whole folder
python scripts/test_voice.py voices "Papa, BP ki goli lijiye"   # compare Timbre voices
```

Record your parents saying the schedule and the replies, slowly and softly, with medicine names. If accuracy is poor, the reply buttons ("Haan, le li" / "10 minute baad") already work without voice.

### Demo shortcut

On `/family`, open "Notification aur demo" and tap **Demo reminder bhejein**. It starts a reminder right now, and if the parent doesn't answer within the seconds you set (default 90), the family alert fires. Good for filming the whole loop in one take.

## Settings (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `GNANI_API_KEY` | | Prisma + Timbre key |
| `STT_LANGUAGE` | `hi-IN` | Prisma language code |
| `TTS_MODEL` / `TTS_VOICE` / `TTS_LANGUAGE` | `timbre-v2.5` / `Poorvi` / `hi-en` | Timbre settings (voices are per model, see the Gnani voice catalog) |
| `REMIND_EVERY_MIN` | 10 | Re-remind if no answer |
| `MAX_REMINDERS` | 3 | Reminders per dose |
| `MISSED_AFTER_MIN` | 30 | Minutes of no answer before the family is alerted |
| `APP_TZ` | `Asia/Kolkata` | Time zone for the schedule |

## How it's built

```
app/
  main.py        FastAPI routes
  parser.py      Hinglish/Hindi/English -> schedule (rules, no LLM) + read-back text
  replies.py     classifies the parent's answer: taken / snooze / symptom / confused / unknown
  service.py     dose events, reminders, snooze, missed-dose alerts, escalation
  scheduler.py   background loop (every 15 s)
  gnani.py       Prisma + Timbre calls (Timbre audio is cached on disk)
  push.py        web push notifications
static/          mobile web pages (green + cream, Noto Sans + Devanagari)
scripts/         test_voice.py, gen_vapid.py, make_icons.py
tests/           parser, replies, reminder logic, API
```

Gnani endpoints used: `POST https://api.vachana.ai/stt/v3` (Prisma v2.5) and `POST https://api.vachana.ai/api/v1/tts/inference` (Timbre). Docs: https://docs.gnani.ai/api/introduction/quick-start

## Tests

```bash
pytest -q
```

## Known limits (be honest about these in the write-up)

- The parser is rule-based. Unusual phrasing can be misread, which is why the read-back and the editable draft exist.
- Reminders need the phone notification (or the page open). The app does not place real phone calls.
- Symptom detection is keyword based and leans toward alerting the family, so it can raise a false alarm (for example "dard nahi hai").
- Prisma accuracy on soft or slow elderly speech and medicine names is untested until you try it on real recordings.
- One household, one parent. No logins.
