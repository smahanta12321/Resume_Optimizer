"""LLM provider + rewriter tests. No network: fake providers and stub SDK clients. Fictional data only."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import httpx2 as httpx
import pytest

from src.config import Settings
from src.schemas.analysis import Importance, JDAnalysis, Requirement, RequirementCategory as Cat
from src.schemas.profile import Bullet, Contact, Experience, MasterProfile, Skill, VerifiedMetric
from src.schemas.resume import TextOrigin
from src.services.llm.anthropic_provider import AnthropicProvider
from src.services.llm.openai_provider import OpenAIProvider
from src.services.llm.provider import LLMError, get_provider, provider_status
from src.services.matching_service import build_match_report
from src.services.resume_generator import build_draft
from src.services.resume_rewriter import OUTPUT_SCHEMA, build_request, rewrite

TODAY = date(2026, 10, 5)


@pytest.fixture
def setup():
    profile = MasterProfile(
        contact=Contact(full_name="Secret Fictional Name", email="secret@example.com", phone="+1 555 0100"),
        summary="Fictional engineer.",
        experience=[Experience(id="exp-1", employer="Hidden Employer Fictional", title="ML Engineer",
                               start_date="2021-01", bullets=[
                                   Bullet(id="bul-1", text="Deployed PyTorch models with Docker."),
                                   Bullet(id="bul-2", text="Cut latency by 40% via batching.",
                                          verified_metrics=[VerifiedMetric(label="latency", value="40%")]),
                               ])],
        skills=[Skill(name="PyTorch"), Skill(name="Docker")],
    )
    analysis = JDAnalysis(job_id="job-1", jd_hash="h", requirements=[
        Requirement(category=Cat.SKILL, text="PyTorch", normalized_term="PyTorch", importance=Importance.REQUIRED),
        Requirement(category=Cat.SKILL, text="Kubernetes", normalized_term="Kubernetes",
                    importance=Importance.REQUIRED)])
    report, _ = build_match_report(analysis, profile, today=TODAY)
    content, _ = build_draft(profile, analysis, report)
    return profile, analysis, report, content


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate_json(self, *, system, user, schema, max_tokens):
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.responses.pop(0)


def _out(summary="ML engineer with 5 years using PyTorch and Docker.", ids=("bul-1",), **bullets):
    return json.dumps({"summary": {"text": summary, "evidence_ids": list(ids)},
                       "bullets": [{"id": k.replace("_", "-"), "text": v} for k, v in bullets.items()]})


# ---- what is sent -----------------------------------------------------------------


def test_request_excludes_contact_and_employer_and_wraps_jd(setup):
    profile, analysis, report, content = setup
    req = build_request(content, profile, analysis, report, "Fictional Role", TODAY)
    sent = req.system + req.user
    for secret in ("Secret Fictional Name", "secret@example.com", "555 0100", "Hidden Employer"):
        assert secret not in sent
    assert "<job_requirements>" in req.user and "untrusted" in req.system
    assert "Documented professional experience: 5 years" in req.user
    assert set(req.bullet_ids) == {"bul-1", "bul-2"}
    payload = json.loads(req.user.split("verified_metrics):\n", 1)[1])
    assert {"latency: 40%"} == set(next(b for b in payload if b["id"] == "bul-2")["verified_metrics"])


# ---- applying rewrites --------------------------------------------------------------


def test_faithful_rewrites_applied_unfaithful_discarded(setup):
    profile, analysis, report, content = setup
    provider = FakeProvider(_out(bul_1="Deployed PyTorch models in Docker containers.",
                                 bul_2="Cut latency by 60% via batching on Kubernetes."))
    result = rewrite(content, profile, analysis, report, provider, today=TODAY)
    bullets = {b.evidence_ids[0]: b for b in result.content.experience[0].bullets}
    assert bullets["bul-1"].origin is TextOrigin.REWRITTEN
    assert bullets["bul-1"].text == "Deployed PyTorch models in Docker containers."
    assert bullets["bul-2"].origin is TextOrigin.VERBATIM and bullets["bul-2"].text == "Cut latency by 40% via batching."
    assert "Rewrite discarded" in bullets["bul-2"].notes[0] and "60" in bullets["bul-2"].notes[0]
    assert (result.rewritten, result.rejected) == (1, 1)
    assert result.content.summary.origin is TextOrigin.REWRITTEN
    assert result.content.summary.evidence_ids == ["bul-1"]


def test_summary_overclaiming_years_is_discarded(setup):
    profile, analysis, report, content = setup
    provider = FakeProvider(_out(summary="ML engineer with 9 years of PyTorch experience."))
    result = rewrite(content, profile, analysis, report, provider, today=TODAY)
    assert result.content.summary.text == "Fictional engineer."
    assert any("discarded" in n for n in result.notes)


def test_summary_must_cite_sent_evidence(setup):
    profile, analysis, report, content = setup
    result = rewrite(content, profile, analysis, report, FakeProvider(_out(ids=("bul-nope",))), today=TODAY)
    assert result.content.summary.origin is TextOrigin.VERBATIM


def test_unknown_bullet_ids_ignored(setup):
    profile, analysis, report, content = setup
    result = rewrite(content, profile, analysis, report, FakeProvider(_out(bul_zzz="Invented.")), today=TODAY)
    assert any("not sent" in n for n in result.notes)
    assert all(b.origin is TextOrigin.VERBATIM for b in result.content.experience[0].bullets)


def test_one_retry_on_malformed_output_then_error(setup):
    profile, analysis, report, content = setup
    ok = FakeProvider("not json", _out())
    rewrite(content, profile, analysis, report, ok, today=TODAY)
    assert len(ok.calls) == 2 and "did not match" in ok.calls[1]["user"]
    bad = FakeProvider("nope", '{"summary": {}}')
    with pytest.raises(LLMError, match="expected format"):
        rewrite(content, profile, analysis, report, bad, today=TODAY)
    assert len(bad.calls) == 2  # bounded


def test_original_content_not_mutated(setup):
    profile, analysis, report, content = setup
    before = content.model_dump()
    rewrite(content, profile, analysis, report, FakeProvider(_out(bul_1="Deployed PyTorch models.")), today=TODAY)
    assert content.model_dump() == before


# ---- provider configuration -------------------------------------------------------


def _settings(**kw):
    return Settings(data_dir=".", output_dir=".", log_level="INFO", **kw)


def test_provider_status(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert not provider_status(_settings()).available
    assert get_provider(_settings()) is None
    assert "Unknown" in provider_status(_settings(llm_provider="other")).message
    assert "RESUME_OPTIMIZER_LLM_MODEL" in provider_status(_settings(llm_provider="openai")).message
    assert not provider_status(_settings(llm_provider="openai", llm_model="m")).available
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    assert provider_status(_settings(llm_provider="openai", llm_model="m")).available
    s = provider_status(_settings(llm_provider="anthropic"))
    assert s.available and s.model == "claude-opus-5-5"
    assert isinstance(get_provider(_settings(llm_provider="anthropic")), AnthropicProvider)


# ---- SDK adapters (stub clients) --------------------------------------------------


class _Recorder:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.kwargs = result, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


def _anthropic_client(result=None, error=None):
    rec = _Recorder(result, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=rec), messages=rec), rec


def _msg(text='{"a": 1}', stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def test_anthropic_request_shape():
    client, rec = _anthropic_client(_msg())
    out = AnthropicProvider("claude-opus-5-5", client=client).generate_json(
        system="s", user="u", schema=OUTPUT_SCHEMA, max_tokens=100)
    assert out == '{"a": 1}'
    assert rec.kwargs["output_config"]["format"] == {"type": "json_schema", "schema": OUTPUT_SCHEMA}
    assert rec.kwargs["fallbacks"] == "default" and rec.kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    client2, rec2 = _anthropic_client(_msg())
    AnthropicProvider("claude-haiku-4-5", client=client2).generate_json(system="s", user="u", schema={}, max_tokens=1)
    assert "fallbacks" not in rec2.kwargs


@pytest.mark.parametrize("stop,match", [("refusal", "declined"), ("max_tokens", "cut off")])
def test_anthropic_stop_reasons(stop, match):
    client, _ = _anthropic_client(_msg(stop=stop))
    with pytest.raises(LLMError, match=match):
        AnthropicProvider("claude-opus-5-5", client=client).generate_json(system="s", user="u", schema={}, max_tokens=1)


def test_anthropic_errors_mapped():
    import anthropic

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    for status, cls, match, retry in [(401, anthropic.AuthenticationError, "API key", False),
                                      (404, anthropic.NotFoundError, "not found", False),
                                      (429, anthropic.RateLimitError, "rate limit", True),
                                      (529, anthropic.APIStatusError, "529", True)]:
        err = cls("x", response=httpx.Response(status, request=req), body=None)
        client, _ = _anthropic_client(error=err)
        with pytest.raises(LLMError, match=match) as exc:
            AnthropicProvider("claude-opus-5-5", client=client).generate_json(system="s", user="u", schema={},
                                                                             max_tokens=1)
        assert exc.value.retryable is retry
    client, _ = _anthropic_client(error=anthropic.APIConnectionError(request=req))
    with pytest.raises(LLMError, match="reach"):
        AnthropicProvider("claude-opus-5-5", client=client).generate_json(system="s", user="u", schema={},
                                                                         max_tokens=1)


def _openai_client(content='{"a": 1}', finish="stop", refusal=None, error=None):
    msg = SimpleNamespace(content=content, refusal=refusal)
    rec = _Recorder(SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)]), error)
    return SimpleNamespace(chat=SimpleNamespace(completions=rec)), rec


def test_openai_request_shape_and_failures():
    client, rec = _openai_client()
    assert OpenAIProvider("fictional-model", client=client).generate_json(
        system="s", user="u", schema=OUTPUT_SCHEMA, max_tokens=50) == '{"a": 1}'
    assert rec.kwargs["response_format"]["json_schema"]["strict"] is True
    assert rec.kwargs["messages"][0] == {"role": "system", "content": "s"}
    for kw, match in [({"refusal": "no"}, "declined"), ({"finish": "length"}, "cut off"), ({"content": ""}, "no text")]:
        client, _ = _openai_client(**kw)
        with pytest.raises(LLMError, match=match):
            OpenAIProvider("m", client=client).generate_json(system="s", user="u", schema={}, max_tokens=1)
