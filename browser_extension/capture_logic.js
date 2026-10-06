/*
 * Pure capture helpers shared by the popup and the Node tests (no DOM access here).
 * Page content is untrusted: everything is reduced to plain text and only ever shown
 * through form-field values (never innerHTML).
 */
(function (root) {
  "use strict";

  const MAX_TEXT = 50000;          // matches the app's MAX_JD_CHARS
  const MIN_SELECTION = 40;        // shorter selections are probably accidental
  const MIN_STRUCTURED = 200;      // structured descriptions shorter than this are likely truncated
  const FIELD_LIMITS = { title: 200, company: 200, location: 200, page_title: 300, url: 2048 };

  const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: "\"", apos: "'", nbsp: " " };

  function decodeEntities(s) {
    return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, function (m, code) {
      if (code[0] === "#") {
        const n = code[1].toLowerCase() === "x" ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10);
        return Number.isFinite(n) && n > 0 && n < 0x110000 ? String.fromCodePoint(n) : "";
      }
      const v = ENTITIES[code.toLowerCase()];
      return v === undefined ? m : v;
    });
  }

  function normalizeText(s) {
    return String(s || "")
      .replace(/\r\n?/g, "\n")
      .replace(/[\t  ]+/g, " ")
      .split("\n").map(function (l) { return l.trim(); }).join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  /** Convert an HTML fragment (e.g. a JobPosting description) to plain text without rendering it. */
  function htmlToText(html) {
    let s = String(html || "");
    s = s.replace(/<(script|style|noscript|template)[\s\S]*?<\/\1\s*>/gi, " ");
    s = s.replace(/<li[^>]*>/gi, "\n• ");
    s = s.replace(/<(br|\/p|\/div|\/li|\/h[1-6]|\/ul|\/ol|\/tr|p|div|h[1-6]|ul|ol|tr)\b[^>]*>/gi, "\n");
    s = s.replace(/<[^>]*>/g, "");
    return normalizeText(decodeEntities(s));
  }

  function asText(v) {
    if (v == null) return "";
    if (typeof v === "string") return v.trim();
    if (Array.isArray(v)) return v.map(asText).filter(Boolean).join(", ");
    if (typeof v === "object") return asText(v.name);
    return String(v).trim();
  }

  function locationOf(posting) {
    const places = [].concat(posting.jobLocation || []);
    const names = [];
    places.forEach(function (p) {
      const a = (p && p.address) || {};
      const parts = typeof a === "string" ? [a]
        : [asText(a.addressLocality), asText(a.addressRegion), asText(a.addressCountry)];
      const name = parts.filter(Boolean).filter(function (x, i, arr) { return arr.indexOf(x) === i; }).join(", ");
      if (name) names.push(name);
    });
    if (/TELECOMMUTE/i.test(asText(posting.jobLocationType))) names.push("Remote");
    return names.filter(function (x, i, arr) { return arr.indexOf(x) === i; }).join("; ");
  }

  function* walk(node) {
    if (Array.isArray(node)) { for (const n of node) yield* walk(n); return; }
    if (node && typeof node === "object") {
      yield node;
      for (const key of ["@graph", "mainEntity", "itemListElement"]) if (key in node) yield* walk(node[key]);
    }
  }

  /** First schema.org JobPosting in a list of JSON-LD script texts, or null. Bad JSON is skipped. */
  function findJobPosting(jsonLdTexts) {
    for (const text of jsonLdTexts || []) {
      let data;
      try { data = JSON.parse(text); } catch (e) { continue; }
      for (const obj of walk(data)) {
        const types = [].concat(obj["@type"] || []);
        if (types.indexOf("JobPosting") !== -1) {
          return {
            title: asText(obj.title),
            company: asText(obj.hiringOrganization),
            location: locationOf(obj),
            descriptionHtml: typeof obj.description === "string" ? obj.description : "",
          };
        }
      }
    }
    return null;
  }

  /** Pick the best source: the user's selection, then structured data, then the page's main text. */
  function chooseText(sources) {
    const selection = normalizeText(sources.selection);
    const structured = normalizeText(sources.structuredText);
    const main = normalizeText(sources.mainText);
    if (selection.length >= MIN_SELECTION) return { text: selection, method: "selection" };
    if (structured.length >= MIN_STRUCTURED) return { text: structured, method: "structured" };
    if (main) return { text: main, method: "page" };
    return { text: structured || selection, method: structured ? "structured" : "selection" };
  }

  /** Validation messages for the popup form (empty list = OK). */
  function validate(fields) {
    const errors = [];
    const text = normalizeText(fields.text);
    if (!text) errors.push("The job description is empty.");
    if (text.length > MAX_TEXT) errors.push("The text is longer than " + MAX_TEXT + " characters. Trim it to the job posting.");
    if (fields.url && !/^https?:\/\//i.test(fields.url)) errors.push("Only http(s) pages can be captured.");
    if (!fields.confirmed) errors.push("Tick the box to confirm you reviewed the text.");
    return errors;
  }

  /** Request body for the local receiver; only the expected fields, trimmed to their limits. */
  function buildPayload(fields, version) {
    const out = { text: normalizeText(fields.text), method: fields.method || "edited",
                  extension_version: String(version || "").slice(0, 20) };
    Object.keys(FIELD_LIMITS).forEach(function (k) {
      out[k] = normalizeText(fields[k]).replace(/\n/g, " ").slice(0, FIELD_LIMITS[k]);
    });
    return out;
  }

  const api = { MAX_TEXT, htmlToText, normalizeText, decodeEntities, findJobPosting, chooseText, validate, buildPayload };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.ResumeCapture = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
