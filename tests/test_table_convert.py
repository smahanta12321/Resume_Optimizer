"""Table <-> model conversion used by the profile editor."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.profile import Achievement, Bullet, Education, Skill, VerifiedMetric
from src.ui.table_convert import (
    models_to_rows,
    parse_metrics,
    rows_to_models,
    split_csv,
)


def test_split_csv():
    assert split_csv(" a, b,,c ") == ["a", "b", "c"]
    assert split_csv(None) == []
    assert split_csv(["x ", ""]) == ["x"]


def test_parse_metrics_valid_and_invalid():
    ms = parse_metrics("queues=12; latency = 35%")
    assert [(m.label, m.value) for m in ms] == [("queues", "12"), ("latency", "35%")]
    assert parse_metrics("") == []
    with pytest.raises(ValueError, match="label=value"):
        parse_metrics("just text")


def test_bullet_round_trip_preserves_ids():
    bullets = [Bullet(id="bul-1", text="Did X", skills=["Python"], verified_metrics=[VerifiedMetric(label="a", value="1")])]
    rows = models_to_rows(
        bullets, ["id", "text", "skills", "source_note", "verified_metrics"],
        list_fields=("skills",), metric_fields=("verified_metrics",),
    )
    assert rows[0]["skills"] == "Python" and rows[0]["verified_metrics"] == "a=1"
    rows[0]["text"] = "Did X better"
    back = rows_to_models(rows, Bullet, bullets, list_fields=("skills",), metric_fields=("verified_metrics",))
    assert back[0].id == "bul-1" and back[0].text == "Did X better"
    assert back[0].verified_metrics == bullets[0].verified_metrics


def test_new_rows_get_ids_and_blank_rows_dropped():
    rows = [{"id": "", "text": "New bullet", "skills": "Go"}, {"id": None, "text": "", "skills": None}]
    out = rows_to_models(rows, Bullet, [], list_fields=("skills",))
    assert len(out) == 1 and out[0].id.startswith("bul-") and out[0].skills == ["Go"]


def test_unshown_fields_preserved():
    ach = Achievement(id="ach-1", title="Award", verified_metrics=[VerifiedMetric(label="rank", value="1st")])
    out = rows_to_models([{"id": "ach-1", "title": "Award (renamed)", "description": "", "date": ""}], Achievement, [ach])
    assert out[0].verified_metrics == ach.verified_metrics
    assert out[0].date is None


def test_none_dates_become_none_and_strings_become_empty():
    out = rows_to_models(
        [{"id": "", "institution": "Uni (fictional)", "degree": "BSc", "field_of_study": None, "start_date": None, "end_date": None}],
        Education, [],
    )
    assert out[0].start_date is None and out[0].field_of_study == ""


def test_invalid_row_raises():
    with pytest.raises(ValidationError):
        rows_to_models([{"id": "", "name": "Go", "category": "not-a-category"}], Skill, [])
