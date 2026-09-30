"""Pure helpers converting between profile models and editable table rows.

Kept free of Streamlit so they can be unit-tested. Rows edited in a table only
overlay the fields shown; any fields not shown (e.g. verified metrics on an
achievement) are preserved from the existing item with the same ID.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Type, TypeVar

from pydantic import BaseModel

from src.schemas.profile import VerifiedMetric

M = TypeVar("M", bound=BaseModel)


def split_csv(value: Any) -> list[str]:
    """'a, b,,c' -> ['a', 'b', 'c']; lists pass through (stripped); None -> []."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value).split(",")
    return [s.strip() for s in items if str(s).strip()]


def join_csv(values: Iterable[str]) -> str:
    return ", ".join(values)


def parse_metrics(value: Any) -> list[VerifiedMetric]:
    """Parse 'label=value; label=value' into verified metrics.

    Raises ValueError for entries that lack '=' so the user notices typos.
    """
    if not value or not str(value).strip():
        return []
    metrics = []
    for part in str(value).split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Metric '{part}' must look like 'label=value'.")
        label, val = part.split("=", 1)
        metrics.append(VerifiedMetric(label=label.strip(), value=val.strip()))
    return metrics


def format_metrics(metrics: Iterable[VerifiedMetric]) -> str:
    return "; ".join(f"{m.label}={m.value}" for m in metrics)


def _is_blank_row(row: dict) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for k, v in row.items() if k != "id")


def rows_to_models(
    rows: list[dict],
    model_cls: Type[M],
    existing: Iterable[M],
    *,
    list_fields: tuple[str, ...] = (),
    metric_fields: tuple[str, ...] = (),
) -> list[M]:
    """Build models from edited table rows, preserving unshown fields by ID.

    Blank rows are dropped. Rows without an ID get a fresh one from the model default.
    Raises pydantic.ValidationError / ValueError on invalid data.
    """
    by_id = {getattr(m, "id"): m for m in existing}
    out: list[M] = []
    for raw in rows:
        row = {k: v for k, v in raw.items()}
        if _is_blank_row(row):
            continue
        row_id: Optional[str] = (row.get("id") or "").strip() or None
        base = by_id[row_id].model_dump() if row_id in by_id else {}
        for f in list_fields:
            if f in row:
                row[f] = split_csv(row[f])
        for f in metric_fields:
            if f in row:
                row[f] = parse_metrics(row[f])
        nullable = _nullable(model_cls)
        for k, v in list(row.items()):
            if v is None and k not in nullable:
                row[k] = ""  # table cells cleared by the user -> empty string fields
        if row_id is None:
            row.pop("id", None)
        out.append(model_cls.model_validate({**base, **row}))
    return out


def _nullable(model_cls: Type[BaseModel]) -> set[str]:
    """Field names whose default is None (dates etc.)."""
    return {name for name, f in model_cls.model_fields.items() if f.default is None}


def models_to_rows(
    models: Iterable[BaseModel],
    columns: list[str],
    *,
    list_fields: tuple[str, ...] = (),
    metric_fields: tuple[str, ...] = (),
) -> list[dict]:
    rows = []
    for m in models:
        row = {}
        for c in columns:
            v = getattr(m, c)
            if c in list_fields:
                v = join_csv(v)
            elif c in metric_fields:
                v = format_metrics(v)
            elif hasattr(v, "value"):  # enums
                v = v.value
            row[c] = v if v is not None else ""
        rows.append(row)
    return rows
