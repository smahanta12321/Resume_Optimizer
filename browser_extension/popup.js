/* Popup: runs only when the user clicks the toolbar button (activeTab). */
"use strict";

const RC = globalThis.ResumeCapture;
const VERSION = chrome.runtime.getManifest().version;
const $ = (id) => document.getElementById(id);
let sources = {};       // method -> text
let original = "";      // text as captured, to detect user edits

function setStatus(kind, message) {
  const el = $("status");
  el.className = kind;
  el.textContent = message;  // textContent only: never interpret page content as HTML
}

/* Runs inside the page the user is viewing. Self-contained: reads visible text only, changes nothing. */
function extractFromPage() {
  const cap = (s, n) => (s || "").slice(0, n);
  const jsonLd = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
    .slice(0, 20).map((s) => cap(s.textContent, 200000));
  const main = document.querySelector("main, article, [role='main']") || document.body;
  return {
    url: location.href,
    pageTitle: cap(document.title, 300),
    selection: cap(String(window.getSelection() || ""), 60000),
    jsonLd,
    mainText: cap(main ? main.innerText : "", 60000),
  };
}

function updateCount() {
  const n = RC.normalizeText($("text").value).length;
  $("count").textContent = `${n.toLocaleString()} characters` + (n > RC.MAX_TEXT ? " (too long)" : "");
  $("send").disabled = !$("confirmed").checked || n === 0 || n > RC.MAX_TEXT;
}

async function init() {
  const cfg = await chrome.storage.local.get({ port: 8765, token: "" });
  if (!cfg.token) {
    setStatus("error", "Not paired yet. Open “Pairing settings” below and paste the token from Resume Optimizer → Settings.");
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https?:/i.test(tab.url || "")) {
    setStatus("error", "This page can't be captured. Open a job posting (http/https) and try again.");
    return;
  }
  let page;
  try {
    [{ result: page }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: extractFromPage });
  } catch (e) {
    setStatus("error", "The browser doesn't allow reading this page. Copy the text and paste it in the app instead.");
    return;
  }
  const posting = RC.findJobPosting(page.jsonLd);
  sources = {
    selection: RC.normalizeText(page.selection),
    structured: posting ? RC.htmlToText(posting.descriptionHtml) : "",
    page: RC.normalizeText(page.mainText),
  };
  const choice = RC.chooseText({ selection: sources.selection, structuredText: sources.structured, mainText: sources.page });
  const labels = { selection: "Your selection", structured: "Job data published by the page", page: "Whole page text" };
  const select = $("source");
  for (const key of ["selection", "structured", "page"]) {
    if (!sources[key]) continue;
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = `${labels[key]} (${sources[key].length.toLocaleString()} chars)`;
    select.appendChild(opt);
  }
  select.value = choice.method;
  $("title").value = (posting && posting.title) || "";
  $("company").value = (posting && posting.company) || "";
  $("location").value = (posting && posting.location) || "";
  $("url").value = page.url;
  $("text").value = original = choice.text;
  $("capture").hidden = false;
  if (cfg.token) {
    setStatus("info", choice.method === "page"
      ? "Using the whole page text. It may include menus or other jobs, so trim it (or select the JD on the page and reopen)."
      : "Review the text, then confirm and send.");
  }
  select.addEventListener("change", () => { $("text").value = original = sources[select.value] || ""; updateCount(); });
  $("text").addEventListener("input", updateCount);
  $("confirmed").addEventListener("change", updateCount);
  $("capture").addEventListener("submit", (ev) => { ev.preventDefault(); send(cfg, page.pageTitle); });
  updateCount();
}

async function send(cfg, pageTitle) {
  const fields = {
    text: $("text").value, title: $("title").value, company: $("company").value, location: $("location").value,
    url: $("url").value, page_title: pageTitle, confirmed: $("confirmed").checked,
    method: $("text").value === original ? $("source").value : "edited",
  };
  const errors = RC.validate(fields);
  if (errors.length) { setStatus("error", errors.join("\n")); return; }
  if (!cfg.token) { setStatus("error", "Not paired. Open “Pairing settings” first."); return; }
  $("send").disabled = true;
  setStatus("info", "Sending…");
  try {
    const resp = await fetch(`http://127.0.0.1:${Number(cfg.port)}/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Resume-Optimizer-Token": cfg.token },
      body: JSON.stringify(RC.buildPayload(fields, VERSION)),
    });
    const body = await resp.json().catch(() => ({}));
    if (resp.ok) {
      setStatus("ok", body.message || "Sent. Review it in Resume Optimizer → Job Import.");
      $("capture").hidden = true;
      return;
    }
    setStatus("error", body.error || `The app refused the capture (HTTP ${resp.status}).`);
  } catch (e) {
    setStatus("error", "Couldn't reach Resume Optimizer. Is the receiver running?\n  python -m src.extension_receiver\n" +
      "Also check the port in Pairing settings and that the extension is enabled in the app's Settings.");
  }
  updateCount();
}

document.addEventListener("DOMContentLoaded", init);
