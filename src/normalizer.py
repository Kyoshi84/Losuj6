"""Wczytywanie i normalizacja danych Lotto (CSV / XLSX) do schematu kanonicznego.

Schemat kanoniczny: draw_id, draw_date (date), n1..n6 (int).
Rekordy niepewne NIE są kasowane po cichu: trafiają do tabeli błędów z powodem.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

NUM_COLS = ["n1", "n2", "n3", "n4", "n5", "n6"]
CANON_COLS = ["draw_id", "draw_date", *NUM_COLS]
MIN_NUM, MAX_NUM = 1, 49

ID_ALIASES = {"draw_id", "id", "nr", "numer", "numer losowania", "nr losowania", "lp"}
DATE_ALIASES = {"draw_date", "date", "data", "data losowania", "data_losowania"}
DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y.%m.%d"]
ENCODINGS = ["utf-8-sig", "utf-8", "cp1250"]


class NormalizationError(Exception):
    """Błąd uniemożliwiający interpretację pliku jako całości."""


@dataclass
class NormalizationResult:
    draws: pd.DataFrame
    errors: pd.DataFrame
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return len(self.draws) > 0


def empty_draws() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="object") for c in CANON_COLS})
    df["draw_id"] = df["draw_id"].astype("Int64")
    for c in NUM_COLS:
        df[c] = df[c].astype("int64")
    return df


# ----------------------------------------------------------------- wczytywanie
def _decode(raw: bytes) -> tuple[str, str]:
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise NormalizationError("Nie udało się odczytać kodowania pliku (UTF-8 / Windows-1250).")


def _read_csv_rows(raw: bytes) -> tuple[list[list[Any]], dict[str, Any]]:
    text, enc = _decode(raw)
    sample = text[:5000]
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in [";", "\t", ","]}
        delim = max(counts, key=counts.get)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return rows, {"format": "csv", "kodowanie": enc, "separator": repr(delim)}


def _read_xlsx_rows(raw: bytes) -> tuple[list[list[Any]], dict[str, Any]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    best, best_name = [], None
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        filled = sum(1 for r in rows if any(v not in (None, "") for v in r))
        if filled > sum(1 for r in best if any(v not in (None, "") for v in r)):
            best, best_name = rows, ws.title
    if not best:
        raise NormalizationError("Żaden arkusz nie zawiera danych.")
    return best, {"format": "xlsx", "arkusz": best_name, "arkusze": [w.title for w in wb.worksheets]}


def load_rows(source: str | Path | bytes, filename: str | None = None) -> tuple[list[list[Any]], dict[str, Any]]:
    if isinstance(source, (str, Path)):
        filename = filename or str(source)
        raw = Path(source).read_bytes()
    else:
        raw = source
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK":
        return _read_xlsx_rows(raw)
    return _read_csv_rows(raw)


# ------------------------------------------------------------------ interpretacja
def _norm(s: Any) -> str:
    return str(s).strip().lower().replace("﻿", "") if s is not None else ""


def detect_layout(header: list[Any]) -> dict[str, Any]:
    """Ustala indeksy kolumn: id, data i sześć liczb. Nie zakłada nazw z góry."""
    h = [_norm(x) for x in header]
    id_idx = next((i for i, x in enumerate(h) if x in ID_ALIASES), None)
    date_idx = next((i for i, x in enumerate(h) if x in DATE_ALIASES), None)
    if date_idx is None:
        raise NormalizationError("Nie znaleziono kolumny z datą losowania (np. 'data' / 'draw_date').")
    if all(c in h for c in NUM_COLS):
        return {"id": id_idx, "date": date_idx, "nums": [h.index(c) for c in NUM_COLS], "metoda": "nazwy n1..n6"}
    # układ jak w Excelu użytkownika: sześć kolumn bezpośrednio po dacie
    return {"id": id_idx, "date": date_idx, "nums": list(range(date_idx + 1, date_idx + 7)),
            "metoda": "sześć kolumn po kolumnie daty"}


def parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"niepoprawna lub niejednoznaczna data: {value!r}")


def parse_int(value: Any) -> int:
    if value is None or str(value).strip() == "":
        raise ValueError("brak wartości")
    f = float(str(value).strip().replace(",", "."))
    if f != int(f):
        raise ValueError(f"liczba niecałkowita: {value!r}")
    return int(f)


def _blank(row: list[Any]) -> bool:
    return all(v is None or str(v).strip() == "" for v in row)


def normalize_rows(rows: list[list[Any]], meta: dict[str, Any] | None = None) -> NormalizationResult:
    meta = dict(meta or {})
    header_i = next((i for i, r in enumerate(rows) if not _blank(r)), None)
    if header_i is None:
        raise NormalizationError("Plik jest pusty.")
    layout = detect_layout(rows[header_i])
    meta["układ kolumn"] = layout["metoda"]

    good: list[dict[str, Any]] = []
    errs: list[dict[str, Any]] = []
    seen_id: dict[int, int] = {}
    seen_sig: dict[tuple, int] = {}
    src_rows = 0
    extra_cols = max((len(r) for r in rows), default=0) - (max(layout["nums"]) + 1)
    if extra_cols > 0:
        meta["dodatkowe kolumny (pominięte)"] = extra_cols

    for line_no, r in enumerate(rows[header_i + 1:], start=header_i + 2):
        if _blank(r):
            continue
        src_rows += 1
        r = list(r) + [None] * (max(layout["nums"]) + 1 - len(r))
        problems: list[str] = []
        draw_id = None
        if layout["id"] is not None:
            try:
                draw_id = parse_int(r[layout["id"]])
            except Exception:
                problems.append(f"niepoprawny numer losowania: {r[layout['id']]!r}")
        date = None
        try:
            date = parse_date(r[layout["date"]])
        except Exception as e:
            problems.append(str(e))
        nums: list[int] = []
        for j in layout["nums"]:
            try:
                nums.append(parse_int(r[j]))
            except Exception as e:
                problems.append(f"kolumna {j + 1}: {e}")
        if len(nums) == 6:
            if any(not MIN_NUM <= x <= MAX_NUM for x in nums):
                problems.append(f"liczba poza zakresem {MIN_NUM}-{MAX_NUM}: {nums}")
            if len(set(nums)) != 6:
                problems.append(f"powtórzona liczba w losowaniu: {nums}")
        if draw_id is not None and draw_id in seen_id:
            problems.append(f"duplikat numeru losowania (pierwszy raz w wierszu {seen_id[draw_id]})")
        sig = (date, tuple(sorted(nums)))
        if date is not None and len(nums) == 6 and sig in seen_sig:
            problems.append(f"duplikat daty i liczb (pierwszy raz w wierszu {seen_sig[sig]})")
        if problems:
            errs.append({"wiersz": line_no, "draw_id": draw_id, "data_źródłowa": r[layout["date"]],
                         "liczby_źródłowe": [r[j] for j in layout["nums"]], "powód": "; ".join(problems),
                         "duplikat": any(p.startswith("duplikat") for p in problems)})
            continue
        if draw_id is not None:
            seen_id[draw_id] = line_no
        seen_sig[sig] = line_no
        good.append({"draw_id": draw_id, "draw_date": date, **dict(zip(NUM_COLS, sorted(nums)))})

    draws = pd.DataFrame(good, columns=CANON_COLS) if good else empty_draws()
    if good:
        draws["draw_id"] = draws["draw_id"].astype("Int64")
        draws = draws.sort_values(["draw_date", "draw_id"], kind="stable").reset_index(drop=True)
    errors = pd.DataFrame(errs, columns=["wiersz", "draw_id", "data_źródłowa", "liczby_źródłowe", "powód", "duplikat"])

    report = build_report(draws, errors, src_rows, meta)
    return NormalizationResult(draws, errors, report)


def build_report(draws: pd.DataFrame, errors: pd.DataFrame, src_rows: int, meta: dict[str, Any]) -> dict[str, Any]:
    gaps: list[int] = []
    if len(draws) and draws["draw_id"].notna().all():
        ids = set(draws["draw_id"].astype(int))
        gaps = [n for n in range(min(ids), max(ids) + 1) if n not in ids]
    n_err = len(errors)
    complete = n_err == 0 and not gaps and len(draws) > 0
    return {
        **meta,
        "rekordów źródłowych": src_rows,
        "poprawnych losowań": len(draws),
        "duplikatów": int(errors["duplikat"].sum()) if n_err else 0,
        "rekordów z błędami": n_err,
        "rekordów do ręcznej weryfikacji": n_err,
        "zakres dat": (f"{draws['draw_date'].min()} – {draws['draw_date'].max()}" if len(draws) else "brak"),
        "luki w numeracji": len(gaps),
        "przykładowe luki": gaps[:10],
        "dane kompletne i gotowe do analizy": "TAK" if complete else
        ("NIE — są błędy lub luki do sprawdzenia" if len(draws) else "NIE — brak poprawnych rekordów"),
    }


def normalize_file(source: str | Path | bytes, filename: str | None = None) -> NormalizationResult:
    rows, meta = load_rows(source, filename)
    if filename or isinstance(source, (str, Path)):
        meta["plik"] = Path(filename or str(source)).name
    return normalize_rows(rows, meta)


def report_to_markdown(result: NormalizationResult) -> str:
    lines = ["# Raport normalizacji — Lotto", ""]
    lines += [f"- {k}: {v}" for k, v in result.report.items()]
    lines += ["", "## Rekordy wymagające weryfikacji"]
    if result.errors.empty:
        lines.append("- brak")
    else:
        lines += [f"- wiersz {r['wiersz']}: {r['powód']}" for _, r in result.errors.iterrows()]
    return "\n".join(lines) + "\n"


def write_canonical_csv(draws: pd.DataFrame, path: str | Path) -> None:
    out = draws.copy()
    out["draw_date"] = pd.to_datetime(out["draw_date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False, encoding="utf-8")


if __name__ == "__main__":  # python -m src.normalizer plik.xlsx wyjscie.csv [raport.md]
    import sys

    res = normalize_file(sys.argv[1])
    write_canonical_csv(res.draws, sys.argv[2])
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(report_to_markdown(res), encoding="utf-8")
    print(res.report)
