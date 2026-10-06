# Resume Optimizer: Capture JD (optional browser extension)

A small Chrome/Edge extension (Manifest V3). It sends the job description **you are looking at** to your **local** AI Resume Optimizer for review. Use it instead of copy-paste; it does nothing a careful copy-paste wouldn't.

## What it does and doesn't do

| It does | It never does |
|---|---|
| Runs only when you click its toolbar button (`activeTab`) | Run in the background, on page load, or on any site you didn't click it on |
| Reads the current page's visible text: your **selection** first, then the page's published job data (schema.org `JobPosting`), then the main page text | Click "see more", scroll, open other pages, or read cookies, history, logins or other tabs |
| Shows everything in an editable preview, and sends only after you tick "I reviewed this text" | Bypass sign-in, paywalls, CAPTCHAs or anti-bot checks. If you can't see it, it can't capture it |
| Sends to `http://127.0.0.1:<port>` (your own computer) with your pairing token | Contact any other server, or load remote code |

Captured content lands in the app's **Job Import → From browser** inbox. It becomes a job only after you review and save it there, with the same duplicate checks as a paste. The extension's script logic converts page HTML to plain text and only ever shows it in form fields; it is never rendered as HTML.

You're responsible for using it in line with each site's terms. It reads only what the site already shows you.

## Install (Chrome or Edge, developer mode)

1. In the app, open **Settings → Browser extension**, turn on **Accept job descriptions from the browser extension**, and click **Save settings**.
2. Start the local receiver in a second terminal, from the project folder with the virtual environment active:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m src.extension_receiver
   ```
   It listens on `127.0.0.1` only (default port 8765, changeable in Settings). Stop it with `Ctrl+C`.
3. Open `chrome://extensions` (or `edge://extensions`), turn on **Developer mode**, click **Load unpacked**, and choose this `browser_extension` folder.
4. Click the extension's **Details → Extension options** (or **Pairing settings** in its popup). Enter the port, paste the **pairing token** from the app's Settings page, click **Save**, then **Test connection**.

## Use

1. Open a job posting. For the cleanest capture, **select the job description text** first.
2. Click the extension icon. Check the source (selection / published job data / whole page), fix the title, company and location if needed, and trim anything that isn't the posting.
3. Tick **I reviewed this text…** and click **Send for review**.
4. In the app: **Job Import → From browser → Review and save**.

## Security notes

- The receiver accepts requests only for host `127.0.0.1`/`localhost`, only from browser-extension origins or non-browser clients (never web pages), and only with the pairing token. It also requires JSON within size limits that passes schema validation. It is off unless enabled in Settings.
- Regenerating the token in Settings un-pairs the extension immediately.
- The extension's permissions are `activeTab`, `scripting`, `storage` and `http://127.0.0.1/*`. Tests in `tests/test_browser_extension.py` keep it that way.

## Develop / test

```bash
node --test tests/js/capture_logic.test.js     # pure capture logic
python -m pytest tests/test_browser_extension.py tests/test_extension_receiver.py tests/test_extension_ui.py
```
