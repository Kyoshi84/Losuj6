"""Eksport CSV / XLSX. Dane eksportowane są dokładnie tymi, które przekazano (widoczne w interfejsie)."""
from __future__ import annotations

import io
from typing import Any

import pandas as pd

from .normalizer import NormalizationResult


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV z BOM, żeby Excel poprawnie wyświetlał polskie znaki."""
    return df.to_csv(index=False).encode("utf-8-sig")


def _fmt_dates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if "date" in c or "data" in c or "wystąpienie" in c:
            out[c] = out[c].astype(str).replace({"None": "", "NaT": ""})
    return out


def build_xlsx_report(result: NormalizationResult, stats: pd.DataFrame | None = None,
                      period_label: str | None = None) -> bytes:
    """Raport XLSX: arkusze Losowania, Błędy, Raport (+ Statystyki, jeśli podano)."""
    buf = io.BytesIO()
    draws = result.draws.copy()
    if "draw_date" in draws:
        draws["draw_date"] = pd.to_datetime(draws["draw_date"]).dt.strftime("%Y-%m-%d")
    errors = result.errors.copy()
    if "liczby_źródłowe" in errors:
        errors["liczby_źródłowe"] = errors["liczby_źródłowe"].astype(str)
    report = pd.DataFrame({"parametr": list(result.report.keys()),
                           "wartość": [_cell(v) for v in result.report.values()]})
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        draws.to_excel(xw, sheet_name="Losowania", index=False)
        errors.to_excel(xw, sheet_name="Błędy", index=False)
        report.to_excel(xw, sheet_name="Raport", index=False)
        if stats is not None:
            sheet = "Statystyki" + (f" {period_label}"[:20] if period_label else "")
            _fmt_dates(stats).to_excel(xw, sheet_name=sheet[:31], index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()


def _cell(v: Any) -> str:
    return ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)
