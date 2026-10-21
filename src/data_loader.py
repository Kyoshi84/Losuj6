"""Wczytywanie już znormalizowanej bazy CSV (schemat kanoniczny) do DataFrame."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .normalizer import CANON_COLS, NUM_COLS, empty_draws


def load_canonical_csv(path: str | Path) -> pd.DataFrame:
    """Zwraca DataFrame z kolumnami draw_id (Int64), draw_date (datetime64), n1..n6 (int).

    Brak pliku lub pusty plik → pusty DataFrame (aplikacja ma się uruchomić i pokazać komunikat).
    """
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return _typed(empty_draws())
    df = pd.read_csv(p, encoding="utf-8-sig")
    missing = [c for c in CANON_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Plik {p.name} nie ma kolumn schematu kanonicznego: {missing}")
    return _typed(df[CANON_COLS])


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["draw_date"] = pd.to_datetime(df["draw_date"])
    df["draw_id"] = df["draw_id"].astype("Int64")
    for c in NUM_COLS:
        df[c] = df[c].astype("int64")
    return df.sort_values(["draw_date", "draw_id"], kind="stable").reset_index(drop=True)
