/* Pairing settings: receiver port and token, stored in this browser profile only. */
"use strict";

const $ = (id) => document.getElementById(id);

function setStatus(kind, message) {
  const el = $("status");
  el.className = kind;
  el.textContent = message;
}

async function load() {
  const cfg = await chrome.storage.local.get({ port: 8765, token: "" });
  $("port").value = cfg.port;
  $("token").value = cfg.token;
}

async function save(ev) {
  ev.preventDefault();
  const port = Number($("port").value);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    setStatus("error", "Port must be between 1024 and 65535.");
    return;
  }
  await chrome.storage.local.set({ port, token: $("token").value.trim() });
  setStatus("ok", "Saved.");
}

async function test() {
  const port = Number($("port").value);
  try {
    const resp = await fetch(`http://127.0.0.1:${port}/health`);
    const body = await resp.json();
    if (body.app !== "resume-optimizer") throw new Error("unexpected");
    setStatus(body.enabled ? "ok" : "error", body.enabled
      ? "Connected. The receiver is running and enabled."
      : "Connected, but the extension is turned off in the app's Settings.");
  } catch (e) {
    setStatus("error", "No receiver on that port. Start it with: python -m src.extension_receiver");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  load();
  $("pairing").addEventListener("submit", save);
  $("test").addEventListener("click", test);
});
