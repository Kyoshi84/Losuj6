"""Źródła danych o wspólnym interfejsie. Silnik statystyczny dostaje zawsze ten sam format."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .api_client import LottoApiClient, map_api_record
from .data_loader import load_canonical_csv
from .normalizer import NormalizationResult, normalize_file, normalize_rows


class LotteryDataSource(ABC):
    name: str = "źródło"

    @abstractmethod
    def load(self) -> NormalizationResult:
        """Zwraca zwalidowane losowania (schemat kanoniczny) oraz tabelę błędów i raport."""


class CsvDataSource(LotteryDataSource):
    """Znormalizowana baza CSV (lub dowolny CSV, który da się znormalizować)."""

    name = "CSV"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> NormalizationResult:
        return normalize_file(self.path)

    def load_database(self) -> pd.DataFrame:
        """Szybkie wczytanie już zwalidowanej bazy."""
        return load_canonical_csv(self.path)


class ExcelDataSource(LotteryDataSource):
    name = "Excel"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> NormalizationResult:
        return normalize_file(self.path)


class ApiDataSource(LotteryDataSource):
    """Źródło API. Pobiera tylko nowe losowania (po `after_draw_id`), jeśli API na to pozwala.

    `client` i `mapper` można wstrzyknąć (testy); domyślne wersje czekają na potwierdzenie specyfikacji.
    """

    name = "API"

    def __init__(self, client: LottoApiClient | None = None,
                 mapper: Callable[[dict[str, Any]], dict[str, Any]] = map_api_record,
                 after_draw_id: int | None = None):
        self.client = client or LottoApiClient()
        self.mapper = mapper
        self.after_draw_id = after_draw_id

    def load(self) -> NormalizationResult:
        raw = self.client.fetch_raw(self.after_draw_id)
        mapped = [self.mapper(r) for r in raw]
        header = ["draw_id", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6"]
        rows = [header] + [[m.get(c) for c in header] for m in mapped]
        return normalize_rows(rows, {"format": "api"})


class FrameSource(LotteryDataSource):
    """Źródło z już znormalizowanego wyniku (np. po wgraniu pliku w interfejsie)."""

    name = "Wgrany plik"

    def __init__(self, result: NormalizationResult, name: str | None = None):
        self._result = result
        if name:
            self.name = name

    def load(self) -> NormalizationResult:
        return self._result
