"""Settings: AI provider, export template, URL import, local-only mode, privacy notice, data export/deletion."""

from __future__ import annotations

import os
from datetime import date

import requests
import streamlit as st

from src.config import LLM_PROVIDERS, PAGE_SIZES, TEMPLATES, Settings, env_var_for, get_settings, setting_default
from src.persistence.extension_token import get_or_create_token, regenerate_token
from src.persistence.settings_store import SettingsError, SettingsStore
from src.services.data_service import delete_everything, export_all_data
from src.services.llm.provider import DEFAULT_MODELS, KEY_ENV, provider_status
from src.ui.state import flash, get_job_store, get_store, show_flashes

EXPORT_KEY = "settings_export_zip"

PRIVACY = """
**Stored on this computer only**
- Master profile and its version history, role profiles, and settings: `{data}`
- Jobs (JD text, source URL, your notes and dates), JD analyses, match reports, resume versions: `{data}/jobs.sqlite3`
- Exported DOCX/PDF files: `{output}`

**Sent elsewhere, only when you trigger it**
- **URL import** fetches the one job page you enter (and that site's robots.txt). No profile data is sent.
- **AI rewriting**, if configured, sends the content shown under *Exactly what will be sent* on Resume Builder,
  and only after you tick the consent box. It never sends your name, contact details, employer names or the
  raw JD text. The provider's own data policy applies to what it receives.
- **Local-only mode** turns both off.
- The optional **browser extension** sends a page's text only to this app on your own computer (127.0.0.1),
  only when you click it and confirm, and it lands in a review inbox.

**Never stored or logged:** API keys (read only from your environment), resume or profile text in logs.
"""


def _locked(settings: Settings, name: str) -> str | None:
    """Explanation if a setting can't be changed here, else None."""
    if settings.sources.get(name) == "env":
        return f"Set by the environment variable {env_var_for(name)}. Edit `.env` to change it."
    return None


def _initial(settings: Settings, stored: dict, name: str):
    """Value to show: the effective one, except while local-only overrides it (then the saved choice)."""
    if settings.sources.get(name) == "local-only":
        return stored.get(name, setting_default(name))
    return getattr(settings, name)


def render() -> None:
    st.title("Settings")
    show_flashes()
    settings = get_settings()
    store = SettingsStore(settings.data_dir)
    stored = store.load()

    with st.form("settings"):
        st.subheader("Privacy")
        local_only = st.toggle("Local-only mode: never contact any external service",
                               value=settings.local_only, disabled=bool(_locked(settings, "local_only")),
                               help=_locked(settings, "local_only") or "Disables URL import and AI rewriting.")

        st.subheader("AI rewriting (optional)")
        provider = st.selectbox("Provider", LLM_PROVIDERS, index=LLM_PROVIDERS.index(_initial(settings, stored,
                                                                                          "llm_provider")),
                                format_func=lambda p: {"none": "None (off)", "anthropic": "Anthropic",
                                                       "openai": "OpenAI"}[p],
                                disabled=bool(_locked(settings, "llm_provider")), help=_locked(settings, "llm_provider"))
        model = st.text_input("Model", value=_initial(settings, stored, "llm_model"),
                              placeholder=f"Default for Anthropic: {DEFAULT_MODELS['anthropic']}",
                              disabled=bool(_locked(settings, "llm_model")),
                              help=_locked(settings, "llm_model") or "Leave blank for the provider default. "
                                                                      "OpenAI needs a model.")
        st.caption("API keys are read only from your environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` in `.env`) "
                   "and are never saved or shown by the app.")

        st.subheader("Resume export")
        c1, c2 = st.columns(2)
        template = c1.radio("Template", TEMPLATES, index=TEMPLATES.index(settings.template), horizontal=True,
                            format_func=lambda t: {"classic": "Classic", "compact": "Compact (tighter spacing)"}[t],
                            disabled=bool(_locked(settings, "template")), help=_locked(settings, "template"))
        page = c2.radio("Paper size", PAGE_SIZES, index=PAGE_SIZES.index(settings.page_size), horizontal=True,
                        disabled=bool(_locked(settings, "page_size")), help=_locked(settings, "page_size"))

        st.subheader("Job import")
        url_import = st.toggle("Allow best-effort import from a job URL",
                               value=_initial(settings, stored, "url_import_enabled"),
                               disabled=bool(_locked(settings, "url_import_enabled")),
                               help=_locked(settings, "url_import_enabled"))

        st.subheader("Browser extension (optional)")
        c1, c2 = st.columns([3, 1])
        ext_enabled = c1.toggle("Accept job descriptions from the browser extension",
                                value=settings.extension_enabled, disabled=bool(_locked(settings, "extension_enabled")),
                                help=_locked(settings, "extension_enabled")
                                or "Lets the local receiver (127.0.0.1 only) put captures in your review inbox.")
        ext_port = c2.number_input("Receiver port", min_value=1024, max_value=65535, step=1,
                                   value=int(settings.extension_port),
                                   disabled=bool(_locked(settings, "extension_port")),
                                   help=_locked(settings, "extension_port"))
        save = st.form_submit_button("Save settings", type="primary")

    if save:
        candidates = {"local_only": local_only, "llm_provider": provider, "llm_model": model, "template": template,
                      "page_size": page, "url_import_enabled": url_import, "extension_enabled": ext_enabled,
                      "extension_port": int(ext_port)}
        changes = {k: v for k, v in candidates.items() if not _locked(settings, k)}
        try:
            store.save(changes)
        except SettingsError as exc:
            st.error(str(exc))
            return
        flash("success", "Settings saved.")
        st.rerun()

    _status(get_settings())
    _extension(get_settings())
    st.subheader("What is stored and what is sent")
    st.markdown(PRIVACY.format(data=settings.data_dir, output=settings.output_dir))
    _data_section(settings, store)


def _status(settings: Settings) -> None:
    status = provider_status(settings)
    (st.success if status.available else st.info)(status.message)
    if settings.local_only:
        st.info("Local-only mode is on: URL import and AI rewriting are disabled.")
    for name, env in KEY_ENV.items():
        st.caption(f"{env}: {'detected' if os.getenv(env) else 'not set'}")


def _data_section(settings: Settings, store: SettingsStore) -> None:
    st.subheader("Your data")
    include_files = st.checkbox("Include exported DOCX/PDF files", value=True)
    if st.button("Prepare data export"):
        st.session_state[EXPORT_KEY] = export_all_data(get_store(), get_job_store(), store, settings.output_dir,
                                                       include_files=include_files)
    data = st.session_state.get(EXPORT_KEY)
    if data:
        st.download_button("Download all my data (.zip)", data=data, mime="application/zip",
                           file_name=f"resume_optimizer_export_{date.today():%Y%m%d}.zip")
        st.caption("The archive contains personal data. Keep it private.")

    with st.expander("Delete everything"):
        st.warning("Permanently deletes your master profile and all its versions, role profiles, all jobs, analyses, "
                   "match reports, resume versions, exported files, and saved settings. This can't be undone. "
                   "Download your data first if you may need it.")
        typed = st.text_input("Type DELETE EVERYTHING to confirm", key="delete-everything-confirm")
        if st.button("Delete all my data", disabled=typed != "DELETE EVERYTHING"):
            result = delete_everything(get_store(), get_job_store(), store, settings.output_dir)
            st.session_state.pop(EXPORT_KEY, None)
            flash("success", f"Deleted all data ({result['jobs']} job(s)).")
            st.rerun()


def receiver_running(port: int) -> bool:
    """Is our receiver answering on 127.0.0.1:port? (Local check only; no external request.)"""
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
        return resp.ok and resp.json().get("app") == "resume-optimizer"
    except (requests.RequestException, ValueError):
        return False


def _extension(settings: Settings) -> None:
    if not settings.extension_enabled:
        return
    st.subheader("Pair the browser extension")
    running = receiver_running(settings.extension_port)
    if running:
        st.success(f"Receiver is running on 127.0.0.1:{settings.extension_port}.")
    else:
        st.warning("Receiver isn't running. Start it in a second terminal (with the virtual environment active):")
        st.code("python -m src.extension_receiver", language="bash")
    token = get_or_create_token(settings.data_dir)
    st.caption("Paste this token and the port into the extension's **Pairing settings**. Treat the token like a "
               "password: anything holding it can add items to your review inbox (nothing else).")
    if st.checkbox("Show pairing token"):
        st.code(token, language=None)
    if st.button("Generate a new token (un-pairs the extension)"):
        regenerate_token(settings.data_dir)
        flash("success", "New token generated. Update it in the extension.")
        st.rerun()
    st.caption("Install: open chrome://extensions (or edge://extensions), turn on Developer mode, click "
               "**Load unpacked**, and choose the `browser_extension` folder. Details: `browser_extension/README.md`.")
