import {
  $, $$, api, enablePush, esc, fmtDay, fmtTime, FOOD_LABEL, ICONS, localNotify, micMessage, onPushMessage,
  registerSW, slotForTime, speak, stopSpeaking, toast, transcribe, unlockAudio, WavRecorder,
} from "./common.js";

const LISTEN_MAX_MS = 25000;
const SLOT_TITLE = { subah: "Subah", dopahar: "Dopahar", shaam: "Shaam", raat: "Raat" };
const STATUS_TEXT = {
  taken: "Le li", due: "Intezaar", snoozed: "Baad mein", missed: "Chhoot gayi", escalated: "Dhyan dein",
};

let label = "Papa";
let recorder = null;
let stopRecording = null;
let lastAlertId = null;

const micBtn = $("#btn-mic");
micBtn.innerHTML = ICONS.mic;

// ---------- Step 1: speak or type the schedule ----------

function micStatus(msg, isErr = false) {
  const el = $("#mic-status");
  el.textContent = msg;
  el.className = "status" + (isErr ? " err" : "");
}

async function toggleMic() {
  await unlockAudio();
  if (recorder && stopRecording) return stopRecording();
  stopSpeaking();
  recorder = new WavRecorder((lvl) => micBtn.style.setProperty("--lvl", lvl));
  try {
    await recorder.start();
  } catch (_) {
    recorder = null;
    return micStatus("Mic ki ijaazat nahi mili. Neeche likhkar bhi bata sakte hain.", true);
  }
  micBtn.classList.add("listening");
  $("#mic-label").textContent = "Sun rahe hain... poora hone par dabaiye";
  micStatus("");
  await new Promise((resolve) => {
    stopRecording = resolve;
    setTimeout(resolve, LISTEN_MAX_MS);
  });
  const rec = await recorder.stop();
  recorder = null;
  stopRecording = null;
  micBtn.classList.remove("listening");
  micBtn.style.setProperty("--lvl", 0);
  $("#mic-label").textContent = "Bolna shuru karein";

  micStatus("Samajh rahe hain...");
  const out = await transcribe(rec);
  if (out.error) return micStatus(micMessage(out.error), true);
  micStatus("");
  $("#schedule-text").value = out.text;
  parse(out.text);
}

async function parse(text) {
  text = (text || "").trim();
  if (!text) return toast("Pehle schedule bolein ya likhein.", true);
  let res;
  try {
    res = await api("/api/schedule/parse", { json: { text } });
  } catch (_) {
    return toast("Schedule samajh nahi paaye. Dobara koshish karein.", true);
  }
  if (!res.items.length) {
    $("#draft-card").hidden = true;
    micStatus("Koi dawai samajh nahi aayi. Aise boliye: subah BP ki goli, raat ko sugar ki goli.", true);
    speak(res.readback).catch(() => {});
    return;
  }
  renderDraft(res.items, res.heard);
  speak($("#readback").textContent).catch(() => {});
}

// ---------- Step 2: edit + confirm ----------

function renderDraft(items, heard) {
  $("#draft-card").hidden = false;
  $("#heard-line").hidden = !heard;
  $("#heard-line").textContent = heard ? `Aapne kaha: "${heard}"` : "";
  $("#draft-rows").innerHTML = "";
  items.forEach(addRow);
  updateReadback();
  $("#draft-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

function addRow(it = { medicine: "", time: "08:00", food: "any", guessed: false }) {
  const row = document.createElement("div");
  row.className = "draft-row" + (it.guessed ? " guessed" : "");
  row.innerHTML = `
    <input type="text" class="d-med" value="${esc(it.medicine)}" placeholder="Dawai ka naam" aria-label="Dawai ka naam">
    <input type="time" class="d-time" value="${esc(it.time)}" aria-label="Time">
    <select class="d-food full" aria-label="Khaane se pehle ya baad">
      <option value="any">Khaane se matlab nahi</option>
      <option value="before">Khaane se pehle</option>
      <option value="after">Khaane ke baad</option>
    </select>
    <div class="tools">
      <span class="muted small d-note"></span>
      <button class="btn sm ghost d-del" type="button">Hatayein</button>
    </div>`;
  row.querySelector(".d-food").value = it.food;
  if (it.guessed) row.querySelector(".d-note").textContent = "Time anumaan se rakha hai, check karein.";
  row.addEventListener("input", updateReadback);
  row.querySelector(".d-del").addEventListener("click", () => { row.remove(); updateReadback(); });
  $("#draft-rows").appendChild(row);
}

function collectDraft() {
  return $$(".draft-row", $("#draft-rows"))
    .map((r) => {
      const time = r.querySelector(".d-time").value;
      return {
        medicine: r.querySelector(".d-med").value.trim(),
        time,
        slot: time ? slotForTime(time) : "subah",
        food: r.querySelector(".d-food").value,
      };
    })
    .filter((i) => i.medicine && i.time);
}

function readbackText(items) {
  if (!items.length) return "Abhi koi dawai nahi hai. '+ Dawai jodein' dabaiye.";
  const parts = items
    .slice()
    .sort((a, b) => a.time.localeCompare(b.time))
    .map((i) => {
      const f = FOOD_LABEL[i.food];
      return `${SLOT_TITLE[i.slot]} ${fmtTime(i.time)}, ${i.medicine}${f ? ", " + f : ""}`;
    });
  return `${label} ke liye: ${parts.join(". ")}. Kya yeh sahi hai?`;
}

function updateReadback() {
  $("#readback").textContent = readbackText(collectDraft());
}

async function confirmSchedule() {
  const items = collectDraft();
  if (!items.length) return toast("Kam se kam ek dawai aur time chahiye.", true);
  try {
    await api("/api/schedule/confirm", { json: { items } });
  } catch (_) {
    return toast("Save nahi ho paaya. Time check karein.", true);
  }
  $("#draft-card").hidden = true;
  $("#schedule-text").value = "";
  toast("Schedule save ho gaya. Reminders shuru.");
  speak(`Theek hai. ${label} ko ab dawai ke time par yaad dilaya jayega.`).catch(() => {});
  loadSchedule();
}

// ---------- schedule, log, alerts ----------

async function loadSchedule() {
  const { items } = await api("/api/schedule");
  $("#sched-count").textContent = items.length ? `${items.length} dawai` : "";
  $("#schedule").innerHTML = items.length
    ? items.map((i) => `
        <li>
          <span class="when">${fmtTime(i.time)}</span>
          <span class="item-main">${esc(i.medicine)}<div class="item-sub">${SLOT_TITLE[i.slot]}${FOOD_LABEL[i.food] ? " · " + FOOD_LABEL[i.food] : ""}</div></span>
          <button class="btn sm ghost" data-del="${i.id}">Hatayein</button>
        </li>`).join("")
    : '<li class="empty">Abhi koi schedule nahi hai. Upar bolkar banayein.</li>';
}

async function loadLog() {
  const { events } = await api("/api/log");
  $("#log").innerHTML = events.length
    ? events.map((e) => `
        <li>
          <span class="when">${fmtDay(e.date)}<div class="item-sub">${fmtTime(e.time)}</div></span>
          <span class="item-main">${esc(e.medicine)}${e.last_reply ? `<div class="item-sub">"${esc(e.last_reply)}"</div>` : ""}</span>
          <span class="chip ${e.status}">${STATUS_TEXT[e.status] || e.status}</span>
        </li>`).join("")
    : '<li class="empty">Abhi tak koi reminder nahi gaya.</li>';
}

async function loadAlerts() {
  const { alerts } = await api("/api/alerts");
  const unseen = alerts.filter((a) => !a.seen);
  $("#alerts-card").hidden = unseen.length === 0;
  $("#alerts").innerHTML = unseen
    .map((a) => `<div class="alert-item"><div>${esc(a.message)}</div><div class="t">${new Date(a.created_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}</div></div>`)
    .join("");

  const newest = alerts.length ? alerts[0].id : 0;
  if (lastAlertId !== null && newest > lastAlertId) {
    const a = alerts[0];
    toast(a.message, true, 6000);
    if (document.hidden) localNotify("Voxelle", a.message, "/family");
  }
  lastAlertId = newest;
}

async function refreshAll() {
  try { await Promise.all([loadLog(), loadAlerts()]); } catch (_) {}
}

// ---------- wiring ----------

micBtn.addEventListener("click", toggleMic);
$("#btn-parse").addEventListener("click", async () => { await unlockAudio(); parse($("#schedule-text").value); });
$("#add-row").addEventListener("click", () => { addRow(); updateReadback(); });
$("#btn-listen").addEventListener("click", async () => { await unlockAudio(); try { await speak($("#readback").textContent); } catch (_) {} });
$("#btn-redo").addEventListener("click", () => {
  $("#draft-card").hidden = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
  toggleMic();
});
$("#btn-confirm").addEventListener("click", confirmSchedule);

$("#schedule").addEventListener("click", async (e) => {
  const id = e.target.dataset && e.target.dataset.del;
  if (!id) return;
  await api(`/api/schedule/${id}`, { method: "DELETE" });
  loadSchedule();
});

$("#save-label").addEventListener("click", async () => {
  const v = $("#parent-label").value.trim() || "Papa";
  const res = await api("/api/settings", { json: { parent_label: v } });
  label = res.parent_label;
  toast(`Ab se "${label}" kaha jayega.`);
  updateReadback();
});

$("#alerts-seen").addEventListener("click", async () => {
  await api("/api/alerts/seen", { method: "POST" });
  loadAlerts();
});

$("#btn-push").addEventListener("click", async () => {
  try {
    const r = await enablePush("family");
    if (!r.ok) {
      toast(r.reason === "denied" ? "Notification ki ijaazat nahi mili. Browser settings mein chalu karein." : "Yeh browser notification support nahi karta.", true, 5000);
    } else if (r.reason === "local_only") {
      toast("Chalu ho gaya, par server par push keys nahi hain. Page khula rakhne par hi dikhega.", false, 6000);
    } else {
      toast("Notification chalu ho gaya.");
    }
  } catch (_) {
    toast("Notification chalu nahi ho paaya.", true);
  }
});

$("#btn-push-test").addEventListener("click", async () => {
  const r = await api("/api/push/test?role=family", { method: "POST" });
  toast(r.sent ? "Test notification bhej diya." : r.push_ready ? "Koi phone registered nahi hai. Pehle 'chalu karein' dabaiye." : "Push keys set nahi hain (scripts/gen_vapid.py chalayein).", !r.sent, 5000);
});

$("#btn-demo").addEventListener("click", async () => {
  const sec = Math.max(30, Number($("#demo-sec").value) || 90);
  await api("/api/demo/fire", { json: { missed_after_sec: sec } });
  toast(`Demo reminder shuru. Parent page kholein. ${sec} second mein jawab nahi diya to yahan alert aayega.`, false, 6000);
  refreshAll();
});

(async function init() {
  registerSW();
  onPushMessage(refreshAll);
  try {
    const cfg = await api("/api/config");
    label = cfg.parent_label;
    $("#parent-label").value = label;
    if (!cfg.voice_ready) micStatus("Voice key abhi set nahi hai. Aap likhkar schedule bana sakte hain.");
  } catch (_) {}
  await Promise.all([loadSchedule(), refreshAll()]);
  setInterval(refreshAll, 6000);
})();
