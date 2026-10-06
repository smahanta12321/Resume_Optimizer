"""Settings resolution (env > settings.json > default), local-only mode, and the settings store."""

from __future__ import annotations

import json

import pytest

from src.config import get_settings
from src.persistence.settings_store import SettingsError, SettingsStore

ENV_VARS = ["RESUME_OPTIMIZER_URL_IMPORT", "RESUME_OPTIMIZER_LLM_PROVIDER", "RESUME_OPTIMIZER_LLM_MODEL",
            "RESUME_OPTIMIZER_PAGE_SIZE", "RESUME_OPTIMIZER_TEMPLATE", "RESUME_OPTIMIZER_LOCAL_ONLY",
            "RESUME_OPTIMIZER_URL_TIMEOUT", "RESUME_OPTIMIZER_LLM_TIMEOUT"]


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    return tmp_path


def test_defaults():
    s = get_settings()
    assert (s.llm_provider, s.page_size, s.template, s.local_only, s.url_import_enabled) == \
        ("none", "A4", "classic", False, True)
    assert set(s.sources.values()) == {"default"}


def test_file_then_env_precedence(clean_env, monkeypatch):
    SettingsStore(clean_env).save({"page_size": "letter", "template": "compact", "llm_provider": "anthropic"})
    s = get_settings()
    assert (s.page_size, s.template, s.llm_provider) == ("Letter", "compact", "anthropic")
    assert s.sources["page_size"] == "file"
    monkeypatch.setenv("RESUME_OPTIMIZER_PAGE_SIZE", "A4")
    s = get_settings()
    assert s.page_size == "A4" and s.sources["page_size"] == "env"
    monkeypatch.setenv("RESUME_OPTIMIZER_TEMPLATE", "")  # blank env does not override
    assert get_settings().template == "compact"


def test_local_only_blocks_network_features(clean_env):
    SettingsStore(clean_env).save({"llm_provider": "anthropic", "url_import_enabled": True, "local_only": True})
    s = get_settings()
    assert s.llm_provider == "none" and s.url_import_enabled is False
    assert s.sources["llm_provider"] == "local-only"


def test_invalid_values_rejected_and_nothing_written(clean_env):
    store = SettingsStore(clean_env)
    with pytest.raises(SettingsError, match="page_size"):
        store.save({"template": "compact", "page_size": "Tabloid"})
    assert store.load() == {}


def test_secrets_cannot_be_saved(clean_env):
    with pytest.raises(SettingsError, match="environment"):
        SettingsStore(clean_env).save({"ANTHROPIC_API_KEY": "sk-not-real"})
    assert not (clean_env / "settings.json").exists()


def test_bad_settings_file_falls_back(clean_env):
    (clean_env / "settings.json").write_text("{not json", encoding="utf-8")
    assert get_settings().page_size == "A4"
    (clean_env / "settings.json").write_text(json.dumps({"page_size": "Tabloid", "junk": 1}), encoding="utf-8")
    s = get_settings()
    assert s.page_size == "A4" and s.sources["page_size"] == "default"


def test_timeouts_clamped(monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_URL_TIMEOUT", "999")
    monkeypatch.setenv("RESUME_OPTIMIZER_LLM_TIMEOUT", "abc")
    s = get_settings()
    assert s.url_timeout_seconds == 30.0 and s.llm_timeout_seconds == 60.0
