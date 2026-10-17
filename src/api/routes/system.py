"""Health, session check and settings (mirrors the Streamlit Settings form; secrets are never returned)."""

from __future__ import annotations

import os

from fastapi import APIRouter

from src.api import deps
from src.api.errors import ApiError
from src.api.models import Health, ProviderStatusView, Session, SettingsPatch, SettingsValues, SettingsView
from src.config import LLM_PROVIDERS, PAGE_SIZES, TEMPLATES, Settings, env_var_for, setting_default
from src.persistence.settings_store import SettingsError
from src.services.llm.provider import DEFAULT_MODELS, KEY_ENV, provider_status

router = APIRouter(tags=["system"])

API_VERSION = 1
FORM_FIELDS = tuple(SettingsValues.model_fields)


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health(ok=True, app="resume-optimizer-api", api_version=API_VERSION)


@router.get("/session", response_model=Session)
def session() -> Session:
    """Succeeds only with a valid session token (checked by the guard)."""
    return Session(ok=True)


def _locked(settings: Settings) -> dict[str, str]:
    return {name: f"Set by the environment variable {env_var_for(name)}. Edit .env to change it."
            for name in FORM_FIELDS if settings.sources.get(name) == "env"}


def provider_view(settings: Settings) -> ProviderStatusView:
    s = provider_status(settings)
    return ProviderStatusView(available=s.available, message=s.message, provider=s.provider, model=s.model)


def _view() -> SettingsView:
    settings = deps.settings()
    stored = deps.settings_store().load()
    values = {name: getattr(settings, name) for name in FORM_FIELDS}
    saved = {name: (stored.get(name, setting_default(name)) if settings.sources.get(name) == "local-only"
                    else values[name]) for name in FORM_FIELDS}
    return SettingsView(
        values=SettingsValues(**values), saved=SettingsValues(**saved),
        sources={k: v for k, v in settings.sources.items()}, locked=_locked(settings),
        provider_status=provider_view(settings),
        keys_detected={env: bool(os.getenv(env)) for env in KEY_ENV.values()},
        llm_providers=list(LLM_PROVIDERS), templates=list(TEMPLATES), page_sizes=list(PAGE_SIZES),
        default_models=dict(DEFAULT_MODELS), data_dir=str(settings.data_dir), output_dir=str(settings.output_dir),
    )


@router.get("/settings", response_model=SettingsView)
def get_settings_view() -> SettingsView:
    return _view()


@router.patch("/settings", response_model=SettingsView)
def patch_settings(body: SettingsPatch) -> SettingsView:
    changes = body.model_dump(exclude_none=True)
    locked = sorted(set(changes) & set(_locked(deps.settings())))
    if locked:
        raise ApiError(409, "setting_locked", "These settings come from environment variables and can only be "
                                              f"changed in .env: {', '.join(locked)}.", {"locked": locked})
    try:
        deps.settings_store().save(changes)
    except SettingsError as exc:
        raise ApiError(422, "invalid_setting", str(exc)) from exc
    return _view()
