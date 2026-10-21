"""Bezpieczne scalanie nowych losowań z bazą CSV (idempotentne, atomowe, z kopią zapasową)."""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from .data_loader import load_canonical_csv
from .data_sources import LotteryDataSource
from .normalizer import CANON_COLS, NUM_COLS, write_canonical_csv


@dataclass
class SyncResult:
    ok: bool
    added: int = 0
    skipped: int = 0
    rejected: int = 0
    message: str = ""


def _key(df: pd.DataFrame) -> pd.Series:
    """Klucz rekordu: draw_id, a gdy brak — data + liczby."""
    ids = df["draw_id"].astype("object")
    fallback = df["draw_date"].astype(str) + "|" + df[NUM_COLS].astype(str).agg("-".join, axis=1) if len(df) else ids
    return ids.where(ids.notna(), fallback).astype(str)


def merge_draws(existing: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Zwraca (wynik, dodane, pominięte). Ponowne scalenie tych samych rekordów niczego nie zmienia."""
    if new.empty:
        return existing, 0, 0
    existing, new = existing.copy(), new.copy()
    existing["draw_date"] = pd.to_datetime(existing["draw_date"])   # jednolity typ daty po obu stronach
    new["draw_date"] = pd.to_datetime(new["draw_date"])
    known = set(_key(existing)) if len(existing) else set()
    k = _key(new)
    mask = ~k.isin(known) & ~k.duplicated()
    fresh = new[mask]
    merged = pd.concat([existing, fresh], ignore_index=True) if len(fresh) else existing
    merged = merged.sort_values(["draw_date", "draw_id"], kind="stable").reset_index(drop=True)
    return merged, int(mask.sum()), int((~mask).sum())


def write_log(log_path: Path, result: SyncResult, source: str) -> None:
    entries = []
    if log_path.exists():
        try:
            entries = json.loads(log_path.read_text(encoding="utf-8"))
        except ValueError:
            entries = []
    entries.append({"czas": dt.datetime.now().isoformat(timespec="seconds"), "źródło": source, **asdict(result)})
    log_path.write_text(json.dumps(entries[-50:], ensure_ascii=False, indent=2), encoding="utf-8")


def sync_into_csv(source: LotteryDataSource, csv_path: str | Path, log_path: str | Path | None = None,
                  allow_partial: bool = False) -> SyncResult:
    """Dołącza nowe losowania do bazy. Baza zmienia się dopiero po pełnej walidacji.

    Błąd źródła lub błędne rekordy (bez allow_partial) → baza pozostaje nietknięta.
    """
    csv_path = Path(csv_path)
    log_path = Path(log_path) if log_path else None

    def finish(res: SyncResult) -> SyncResult:
        if log_path:
            write_log(log_path, res, source.name)
        return res

    try:
        norm = source.load()
    except Exception as e:  # noqa: BLE001 — każdy błąd źródła ma zostawić bazę w spokoju
        return finish(SyncResult(False, message=f"Pobieranie nie powiodło się: {e}"))

    rejected = len(norm.errors)
    if rejected and not allow_partial:
        return finish(SyncResult(False, rejected=rejected,
                                 message=f"Odrzucono aktualizację: {rejected} rekordów nie przeszło walidacji."))
    existing = load_canonical_csv(csv_path)
    merged, added, skipped = merge_draws(existing, norm.draws)
    if added:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        if csv_path.exists():
            shutil.copy2(csv_path, csv_path.with_suffix(f".bak-{dt.datetime.now():%Y%m%d-%H%M%S}.csv"))
        fd, tmp = tempfile.mkstemp(dir=csv_path.parent, suffix=".tmp")
        os.close(fd)
        try:
            write_canonical_csv(merged[CANON_COLS], tmp)
            os.replace(tmp, csv_path)  # zapis atomowy
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return finish(SyncResult(True, added, skipped, rejected,
                             f"Dodano {added}, pominięto {skipped} (już były w bazie), odrzucono {rejected}."))


def replace_database(draws: pd.DataFrame, csv_path: str | Path) -> Path | None:
    """Zastępuje bazę nowym zestawem (po wcześniejszej walidacji). Zwraca ścieżkę kopii zapasowej."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if csv_path.exists():
        backup = csv_path.with_suffix(f".bak-{dt.datetime.now():%Y%m%d-%H%M%S}.csv")
        shutil.copy2(csv_path, backup)
    fd, tmp = tempfile.mkstemp(dir=csv_path.parent, suffix=".tmp")
    os.close(fd)
    try:
        write_canonical_csv(draws[CANON_COLS], tmp)
        os.replace(tmp, csv_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return backup
