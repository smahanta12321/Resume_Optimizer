# Assisted Apply spike results — Milestone 0 (IN PROGRESS, NOT PASSED)

**Status:** incomplete. S2 passed (automated). S1, S3 and S4 await the owner's manual run. Milestone 1 is
blocked until every row below is recorded and the owner approves. Rows are evaluated independently: a
result for one browser or one ATS is never inferred from another. Any row that can't be verified stays
**UNVERIFIED** and the spike stays incomplete.

**Tested baseline (decision (a), 2026-10-11):** `minimum_chrome_version` = `"155"`. This is the version
actually tested (Chrome 155.0.8059.39, Edge 155.0.4283.45), documented as a tested baseline, **not** a
proven technical minimum. Version 116 was not tested.

Throwaway kit (outside the repo, never merged):
`%TEMP%\claude\d--Resume-Optimizer\413ded3c-5734-4b2e-b7b0-95773575008d\scratchpad\ro-spike\`
(`ext\` spike extension, `ext2\` identical copy that gets a different ID, `mock\mock_upload.html`,
`origin_echo.py`, `spike_s2.py`). No product code has been written; the plan and this file are uncommitted.

Result values: **PASS**, **FAIL**, **UNVERIFIED** (could not be checked, or the site accepted the file but
completion couldn't be confirmed), **NOT YET RUN**.

When reporting results, never include pairing tokens, cookies, passwords, session data or personal
application data. Panel output contains only extension IDs, origins, file counts and the fictional file name.

## S1 — side panel can use the toolbar-click (`activeTab`) grant

| # | Check | Chrome 155 | Edge 155 |
|---|---|---|---|
| S1.1 | Toolbar click → "SPIKE: open side panel" → panel opens for this tab | PASS (2026-10-12, panel opened; Chrome 155.0.8059.39 Official Build 64-bit per chrome://version, Windows 11 25H2; tab 377561429) | NOT YET RUN |
| S1.2 | Panel `executeScript` on the mock page → `S1 OK` | PASS (`S1 OK: http://localhost:8999/mock_upload.html`) | NOT YET RUN |
| S1.3 | After SPA hash change (`#step2`) → still `S1 OK` | PASS (`S1 OK: http://localhost:8999/mock_upload.html#step2`) | NOT YET RUN |
| S1.4 | After full navigation to another origin → clean `S1 FAIL` message, panel keeps working | PASS (on example.com: `S1 FAIL: Cannot access contents of the page. Extension manifest must request permission to access the respective host.` Caught error, panel still responsive) | NOT YET RUN |

Pass rule per browser: S1.1–S1.4 all PASS. Fail on either browser → popup-based fallback (spec §2.3) for
that design; broad host permissions are not an option.

## S2 — programmatic file attach and controlled inputs (synthetic page)

| # | Check | Chrome 155.0.8059.39 | Edge 155.0.4283.45 |
|---|---|---|---|
| S2.1 | Main world: `DataTransfer` → `input.files`; `files=1`, correct name | PASS | PASS |
| S2.2 | Main world: page listeners got `input` + `change` (`isTrusted=false`); page's own "uploaded" chip appeared | PASS | PASS |
| S2.3 | Isolated world (CDP `Page.createIsolatedWorld`, the content-script mechanism): attach works; main-world listeners received the events; chip appeared | PASS | PASS |
| S2.4 | React-style controlled input: naive `el.value=` + `input` is reverted by the re-render | PASS (reverted to "") | PASS (reverted to "") |
| S2.5 | Native prototype setter + `input`: value and component state kept (main world and isolated world) | PASS | PASS |
| S2.6 | Inside the real spike extension (toolbar grant + panel "attach") on the mock page; chip appears | PASS (2026-10-12: `ATTACH: files=1 name=Fictional_Spike_Resume.pdf`; native input shows the file; page's own indicator "✓ Fictional_Spike_Resume.pdf uploaded" appeared) | NOT YET RUN |

Method for S2.1–S2.5: Playwright 1.63.0 (`.venv` only) driving the installed browsers via `channel=`,
headless, all network blocked except the synthetic page. Script: `ro-spike\spike_s2.py`.

## S3 — live ATS upload indicator (real posting, **no submission**)

Each cell is independent. For a PASS, record the file-input selector and the ATS's own upload-complete
indicator selector (and any error indicator seen). Remove the file and close the tab afterwards.

| ATS | Chrome 155 | Edge 155 | File input selector | Upload-complete indicator | Error indicator / notes |
|---|---|---|---|---|---|
| Greenhouse | NOT YET RUN | NOT YET RUN | | | |
| Lever | NOT YET RUN | NOT YET RUN | | | |
| Ashby | NOT YET RUN | NOT YET RUN | | | |
| Workday (owner signs in) | NOT YET RUN | NOT YET RUN | | | |

Rule: an adapter gets `uploadVerified: true` only if its row is PASS on **both** browsers. Otherwise it
stays `false` (always `upload_unconfirmed` + manual download-and-attach), and the limitation is recorded
here. A filename appearing in `input.files` alone is never a PASS.

## S4 — pairing origin: match **and** rejection

Run `python origin_echo.py` once unpinned to see the origin, then restart it as
`python origin_echo.py --pin <ext\ runtime.id>`.

| # | Check | Chrome 155 | Edge 155 |
|---|---|---|---|
| S4.1 | `ext` panel S4: seen Origin == `chrome-extension://<runtime.id>` → HTTP 200 MATCH | PASS (2026-10-12: RO SPIKE runtime.id `cnicjodonhneadjbkhjaddllhcfdchhf`; helper saw Origin `chrome-extension://cnicjodonhneadjbkhjaddllhcfdchhf`, pinned to the same → `HTTP 200 verdict=MATCH (PASS)`) | NOT YET RUN |
| S4.2 | `ext2` (different extension ID) panel S4 → HTTP 403 REJECTED | PASS (2026-10-12: chrome://extensions maps `ejffjchnpmfomipjmcgfkgkddobbfkfo` = RO SPIKE 2 (ext2), `cnicjodonhneadjbkhjaddllhcfdchhf` = RO SPIKE (ext). ext2 sent Origin `chrome-extension://ejffjchnpmfomipjmcgfkgkddobbfkfo` (= its runtime.id) and got `HTTP 403 REJECTED` while pinned to ext's ID. Note: this Chrome profile is managed by an organization; unpacked extensions and sidePanel were still allowed) | NOT YET RUN |
| S4.3 | Mock page button (web origin `http://localhost:8999`) → HTTP 403 REJECTED | PASS (2026-10-12: `HTTP 403: origin=http://localhost:8999 verdict=REJECTED`, helper pinned to `cnicjodonhneadjbkhjaddllhcfdchhf`) | NOT YET RUN |

Helper self-test (automated, simulated headers): pinned ID → 200; other extension ID → 403; web origin →
403; no Origin → 403. This only checks the helper's logic; S4.1–S4.3 must still be run in the browsers.
The product's own pairing tests (plan Tasks 6, 9, 16) separately assert that a different extension origin,
a web origin and a missing Origin are refused on `/pair/hello` and every `/apply/*` route, and that only the
Settings action can change the pinned ID.

## Findings so far

1. **Plan fixture bug found and fixed.** The planned React-tracker fixture re-rendered only on `blur`,
   which never fires for an unfocused input, so it would have given a false pass. The fixture now
   re-renders after every `input` event (real React behavior); the plan's Task 19 fixture and Task 20
   sanity check were updated. Verified: naive assignment reverts, native setter persists.
2. Script-dispatched events arrive with `isTrusted=false`; the synthetic page accepted them. Whether each
   live ATS does is exactly what S3 checks.
3. Branded Chrome/Edge 155 don't load unpacked extensions from the command line, so S1/S4/S2.6 can't be
   automated here; Playwright's bundled Chromium download timed out on this network.

## Decisions

- S2 PASS → resume attachment stays in scope as **experimental**; every adapter starts
  `uploadVerified: false`.
- S1 → pending. S3 → pending per ATS and per browser. S4 → pending (FAIL ⇒ pairing redesign before
  Milestone 2).
- **Milestone 1 not started.** Awaiting manual results and the owner's explicit approval.
