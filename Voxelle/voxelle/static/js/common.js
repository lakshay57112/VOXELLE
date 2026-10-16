// Shared helpers: API calls, voice recording (WAV), speaking, push, small UI bits.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) {
    o.method = o.method || "POST";
    o.headers = { "Content-Type": "application/json", ...(o.headers || {}) };
    o.body = JSON.stringify(o.json);
    delete o.json;
  }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch (_) {}
  if (!r.ok) {
    const err = new Error((data && data.error) || `http_${r.status}`);
    err.status = r.status;
    throw err;
  }
  return data;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function toast(msg, isErr = false, ms = 3200) {
  let host = $(".toast-host");
  if (!host) {
    host = document.createElement("div");
    host.className = "toast-host";
    document.body.appendChild(host);
  }
  const t = document.createElement("div");
  t.className = "toast" + (isErr ? " err" : "");
  t.textContent = msg;
  host.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

// ---------- time helpers (same wording as the backend read-back) ----------

export function fmtTime(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const h12 = h % 12 || 12;
  return m === 0 ? `${h12} baje` : `${h12}:${String(m).padStart(2, "0")} baje`;
}

export function slotForTime(hhmm) {
  const h = Number(hhmm.split(":")[0]);
  if (h >= 4 && h < 12) return "subah";
  if (h >= 12 && h < 16) return "dopahar";
  if (h >= 16 && h < 20) return "shaam";
  return "raat";
}

export function fmtDay(isoDate) {
  const d = new Date(isoDate + "T00:00:00");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today - d) / 86400000);
  if (diff === 0) return "Aaj";
  if (diff === 1) return "Kal";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export const FOOD_LABEL = { before: "khaane se pehle", after: "khaane ke baad", any: "" };

// ---------- speaking: Timbre via the server, browser voice as a fallback ----------

const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
const player = new Audio();
player.preload = "auto";
let unlocked = false;

// Call from a tap: lets later audio play without another tap (needed on iPhone).
export async function unlockAudio() {
  if (unlocked) return;
  try {
    player.src = SILENT_WAV;
    await player.play();
    unlocked = true;
  } catch (_) {}
}

export function stopSpeaking() {
  try { player.pause(); } catch (_) {}
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}

function browserSpeak(text) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) return resolve(false);
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "hi-IN";
    u.rate = 0.9;
    u.onend = () => resolve(true);
    u.onerror = () => resolve(false);
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  });
}

// Resolves true when finished. Throws NotAllowedError if the browser needs a tap first.
export async function speak(text) {
  stopSpeaking();
  let blobUrl = null;
  try {
    const r = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("tts_" + r.status);
    blobUrl = URL.createObjectURL(await r.blob());
    player.src = blobUrl;
    await player.play();
    await new Promise((resolve) => {
      player.onended = resolve;
      player.onerror = resolve;
    });
    return true;
  } catch (e) {
    if (e && e.name === "NotAllowedError") throw e;
    return browserSpeak(text);
  } finally {
    if (blobUrl) URL.revokeObjectURL(blobUrl);
  }
}

// ---------- recording: mic -> 16 kHz mono WAV (Prisma accepts WAV) ----------

export class WavRecorder {
  constructor(onLevel) {
    this.onLevel = onLevel;
    this.chunks = [];
    this.peak = 0;
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    const AC = window.AudioContext || window.webkitAudioContext;
    this.ctx = new AC();
    await this.ctx.resume();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.node.onaudioprocess = (e) => {
      const data = new Float32Array(e.inputBuffer.getChannelData(0));
      this.chunks.push(data);
      let max = 0;
      for (let i = 0; i < data.length; i++) max = Math.max(max, Math.abs(data[i]));
      this.peak = Math.max(this.peak, max);
      if (this.onLevel) this.onLevel(Math.min(1, max * 3));
    };
    src.connect(this.node);
    this.node.connect(this.ctx.destination); // output stays silent
  }

  async stop() {
    try { this.node.disconnect(); } catch (_) {}
    this.stream.getTracks().forEach((t) => t.stop());
    const rate = this.ctx.sampleRate;
    await this.ctx.close();
    if (this.onLevel) this.onLevel(0);
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const all = new Float32Array(total);
    let off = 0;
    for (const c of this.chunks) { all.set(c, off); off += c.length; }
    return { blob: encodeWav(downsample(all, rate, 16000), 16000), peak: this.peak, seconds: total / rate };
  }

  cancel() {
    try { this.node.disconnect(); } catch (_) {}
    try { this.stream.getTracks().forEach((t) => t.stop()); } catch (_) {}
    try { this.ctx.close(); } catch (_) {}
  }
}

function downsample(buf, from, to) {
  if (from === to) return buf;
  const ratio = from / to;
  const out = new Float32Array(Math.floor(buf.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, buf.length - 1);
    out[i] = buf[i0] + (buf[i1] - buf[i0]) * (pos - i0);
  }
  return out;
}

function encodeWav(samples, rate) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const w = (o, s) => [...s].forEach((c, i) => view.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true);
  w(8, "WAVE"); w(12, "fmt "); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  w(36, "data"); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

// Speech -> text through Prisma. Returns { text } or { error }.
export async function transcribe(recording) {
  if (recording.peak < 0.015) return { error: "quiet" };
  const fd = new FormData();
  fd.append("audio", recording.blob, "speech.wav");
  try {
    const { transcript } = await api("/api/stt", { method: "POST", body: fd });
    return transcript ? { text: transcript } : { error: "empty" };
  } catch (e) {
    return { error: e.message === "no_api_key" ? "no_key" : "failed" };
  }
}

export function micMessage(err) {
  return {
    quiet: "Awaaz bahut dheemi thi. Mic ke paas aakar dobara boliye.",
    empty: "Kuch sunai nahi diya. Dobara boliye.",
    no_key: "Voice key nahi lagi hai. Neeche likhkar bhi bata sakte hain.",
    failed: "Awaaz samajhne mein dikkat hui. Dobara koshish karein ya likhkar bhejein.",
  }[err] || "Kuch gadbad hui.";
}

// ---------- notifications ----------

function urlB64ToUint8(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export async function registerSW() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    const reg = await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
    return reg;
  } catch (_) {
    return null;
  }
}

// role: "parent" | "family". Returns { ok, reason }.
export async function enablePush(role) {
  if (!("Notification" in window) || !("PushManager" in window)) return { ok: false, reason: "unsupported" };
  const reg = await registerSW();
  if (!reg) return { ok: false, reason: "unsupported" };
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return { ok: false, reason: "denied" };
  const cfg = await api("/api/config");
  if (!cfg.push_ready) return { ok: true, reason: "local_only" }; // in-page alerts still work
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8(cfg.vapid_public_key),
    });
  }
  await api("/api/push/subscribe", { json: { role, subscription: sub.toJSON() } });
  return { ok: true, reason: "push" };
}

// Fallback when real push is not set up: show a notification while the page is open in the background.
export async function localNotify(title, body, url) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const reg = await registerSW();
  if (reg) reg.showNotification(title, { body, icon: "/static/icon-192.png", tag: "local", renotify: true, data: { url } });
}

export function onPushMessage(fn) {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", (e) => e.data && e.data.type === "push" && fn());
  }
}

export const ICONS = {
  mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  stop: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
};
