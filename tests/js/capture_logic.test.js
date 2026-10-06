// Node tests for browser_extension/capture_logic.js. Run: node --test tests/js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const RC = require("../../browser_extension/capture_logic.js");

test("htmlToText strips tags and scripts, keeps structure, decodes entities", () => {
  const html = "<p>Fictional Corp &amp; partners</p><script>alert('x')</script><ul><li>Python</li><li>SQL&nbsp;</li></ul>" +
    "<img src=x onerror=alert(1)>Done &#8211; ok &#x2713;";
  const text = RC.htmlToText(html);
  assert.equal(text, "Fictional Corp & partners\n\n• Python\n\n• SQL\n\nDone – ok ✓");
  assert.ok(!text.includes("<") && !text.includes("alert"));
});

test("findJobPosting handles @graph, type arrays and bad JSON", () => {
  const good = JSON.stringify({ "@graph": [{ "@type": "Organization", name: "x" }, {
    "@type": ["JobPosting"], title: "Data Engineer", hiringOrganization: { name: "Fictional Corp" },
    jobLocation: [{ address: { addressLocality: "Pune", addressCountry: "IN" } }], jobLocationType: "TELECOMMUTE",
    description: "<p>Build pipelines.</p>" }] });
  const p = RC.findJobPosting(["{not json", good]);
  assert.deepEqual(p, { title: "Data Engineer", company: "Fictional Corp", location: "Pune, IN; Remote",
                        descriptionHtml: "<p>Build pipelines.</p>" });
  assert.equal(RC.findJobPosting(['{"@type":"Organization"}']), null);
  assert.equal(RC.findJobPosting(undefined), null);
});

test("chooseText prefers selection, then structured, then page", () => {
  const long = "x ".repeat(150);
  assert.equal(RC.chooseText({ selection: "A selected fictional job description that is long enough.",
                               structuredText: long, mainText: "page" }).method, "selection");
  assert.equal(RC.chooseText({ selection: "short", structuredText: long, mainText: "page" }).method, "structured");
  assert.equal(RC.chooseText({ selection: "", structuredText: "tiny", mainText: "Whole page" }).method, "page");
  assert.deepEqual(RC.chooseText({}), { text: "", method: "selection" });
});

test("validate requires text, confirmation, http(s) url and a size limit", () => {
  assert.deepEqual(RC.validate({ text: "JD", url: "https://x.example/j", confirmed: true }), []);
  const errs = RC.validate({ text: "  ", url: "file:///etc/passwd", confirmed: false });
  assert.equal(errs.length, 3);
  assert.equal(RC.validate({ text: "a".repeat(RC.MAX_TEXT + 1), confirmed: true }).length, 1);
});

test("buildPayload sends only expected fields within limits", () => {
  const p = RC.buildPayload({ text: " Fictional JD \n\n\n\n more ", title: "T".repeat(500), company: "C\nD",
                              url: "https://x.example", page_title: "P", location: "", method: "edited",
                              confirmed: true, cookies: "nope" }, "0.1.0");
  assert.deepEqual(Object.keys(p).sort(), ["company", "extension_version", "location", "method", "page_title",
                                            "text", "title", "url"]);
  assert.equal(p.text, "Fictional JD\n\nmore");
  assert.equal(p.title.length, 200);
  assert.equal(p.company, "C D");
});
