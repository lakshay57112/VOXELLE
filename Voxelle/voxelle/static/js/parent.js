import {
  $, api, enablePush, fmtTime, FOOD_LABEL, ICONS, localNotify, micMessage, onPushMessage, registerSW,
  speak, stopSpeaking, toast, transcribe, unlockAudio, WavRecorder,
} from "./common.js";

const LISTEN_MS = 7000;

let started = false;
let label = "Papa";
let current = null; // the reminder on screen
let lastKey = null; // "eventId:remindCount" we already announced
let busy = false; // speaking, listening or sending
let recorder = null;
let stopListeningNow = null;

const micBtn = $("#btn-mic");
micBtn.innerHTML = ICONS.mic;

function setStatus(msg, isErr = false) {
  const el = $("#listen-status");
  el.textContent = msg;
  el.className = "status" + (isErr ? " err" : "");
}

function setSay(msg, warn = false) {
  const el = $("#say-line");
  el.textContent = msg;
  el.className = "say" + (warn ? " warn" : "");
}

// ---------- rendering ----------

function render(state) {
  label = state.parent_label;
  $("#greet").textContent = `Namaste ${label}`;
  const ev = state.event;
  const idle = $("#idle");
  const card = $("#reminder");

  if (ev) {
    current = ev;
    card.hidden = false;
    idle.hidden = true;
    $("#rem-title").textContent = ev.medicine;
    const food = FOOD_LABEL[ev.food];
    $("#rem-detail").textContent =
      `${ev.slot[0].toUpperCase() + ev.slot.slice(1)} ki dawai, ${fmtTime(ev.due_time)}` + (food ? `, ${food}` : "");
    if (started && !busy) {
      const key = `${ev.id}:${ev.remind_count}`;
      if (key !== lastKey) {
        lastKey = key;
        if (document.hidden) localNotify("Dawai ka time", ev.body, "/parent");
        announce(ev);
      }
    }
  } else {
    current = null;
    lastKey = null;
    card.hidden = true;
    if (started) {
      idle.hidden = false;
      const n = state.next;
      $("#next-dose").textContent = n
        ? `Agli dawai: ${n.day} ${fmtTime(n.time)}, ${n.medicine}`
        : "Abhi koi schedule nahi hai. Parivaar se schedule banwa lijiye.";
    }
  }
}

async function refresh() {
  try {
    render(await api("/api/parent/state"));
  } catch (_) {
    setStatus("Server se connection nahi ho paaya.", true);
  }
}

// ---------- speaking the reminder, then listening ----------

async function announce(ev) {
  busy = true;
  setStatus("");
  setSay("");
  try {
    await speak(ev.say);
  } catch (_) {
    // browser wants a tap before it will play sound
    setStatus("Awaaz sunne ke liye 'Dobara sunein' dabaiye.");
    busy = false;
    return;
  }
  busy = false;
  if (current && current.id === ev.id) listen(); // wait for the answer, hands-free
}

async function listen() {
  if (busy || !current) return;
  busy = true;
  micBtn.classList.add("listening");
  $("#mic-label").textContent = "Sun rahe hain... boliye";
  setStatus("Boliye. Poora hone par mic dabaiye.");
  $("#heard").hidden = true;

  recorder = new WavRecorder((lvl) => micBtn.style.setProperty("--lvl", lvl));
  try {
    await recorder.start();
  } catch (_) {
    endListening();
    setStatus("Mic ki ijaazat nahi mili. Button dabakar ya likhkar bataiye.", true);
    return;
  }

  await new Promise((resolve) => {
    stopListeningNow = resolve;
    setTimeout(resolve, LISTEN_MS);
  });
  const rec = await recorder.stop();
  recorder = null;
  stopListeningNow = null;
  endListening();

  setStatus("Samajh rahe hain...");
  const out = await transcribe(rec);
  if (out.error) {
    setStatus(micMessage(out.error), true);
    return;
  }
  $("#heard").textContent = `Aapne kaha: "${out.text}"`;
  $("#heard").hidden = false;
  await sendReply({ text: out.text });
}

function endListening() {
  busy = false;
  micBtn.classList.remove("listening");
  micBtn.style.setProperty("--lvl", 0);
  $("#mic-label").textContent = "Bolkar batayein";
}

// ---------- sending the answer ----------

async function sendReply(payload) {
  if (!current) return;
  setStatus("");
  busy = true;
  let res;
  try {
    res = await api("/api/parent/reply", { json: { event_id: current.id, ...payload } });
  } catch (_) {
    busy = false;
    setStatus("Jawab bhej nahi paaye. Dobara koshish karein.", true);
    return;
  }
  const bad = res.outcome === "symptom" || res.outcome === "confused";
  setSay(res.say, bad);
  try { await speak(res.say); } catch (_) {}
  busy = false;
  if (res.outcome === "unknown") {
    setStatus("Button dabakar bhi bata sakte hain.");
    return;
  }
  $("#heard").hidden = true;
  await refresh();
  setTimeout(() => setSay(""), bad ? 20000 : 9000);
}

// ---------- events ----------

$("#start").addEventListener("click", async () => {
  started = true;
  $("#start-card").hidden = true;
  await unlockAudio();
  // ask for the mic now, while the person is tapping, so later hands-free listening works
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((t) => t.stop());
  } catch (_) {}
  const push = await enablePush("parent").catch(() => ({ ok: false }));
  if (push.ok && push.reason === "local_only") toast("Notification chalu. Page khula rakhein.");
  if (!push.ok) toast("Notification band hai. Page khula rakhne par awaaz aayegi.", false, 4500);
  await refresh();
});

$("#rem-play").addEventListener("click", async () => {
  if (!current) return;
  await unlockAudio();
  if (recorder) return;
  busy = true;
  try { await speak(current.say); } catch (_) {}
  busy = false;
  listen();
});

$("#btn-yes").addEventListener("click", async () => {
  stopSpeaking();
  await unlockAudio();
  sendReply({ action: "taken" });
});

$("#btn-later").addEventListener("click", async () => {
  stopSpeaking();
  await unlockAudio();
  sendReply({ action: "snooze", minutes: 10 });
});

micBtn.addEventListener("click", async () => {
  await unlockAudio();
  if (recorder && stopListeningNow) {
    stopListeningNow(); // tap again to finish
    return;
  }
  stopSpeaking();
  busy = false;
  listen();
});

$("#type-send").addEventListener("click", () => {
  const v = $("#type-input").value.trim();
  if (!v) return;
  $("#type-input").value = "";
  $("#heard").textContent = `Aapne likha: "${v}"`;
  $("#heard").hidden = false;
  sendReply({ text: v });
});

document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
onPushMessage(refresh);
registerSW();
refresh();
setInterval(refresh, 4000);
