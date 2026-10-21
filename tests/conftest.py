"""Dane testowe są SZTUCZNE — nie są prawdziwymi wynikami Lotto."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalizer import normalize_rows  # noqa: E402

# 5 sztucznych losowań (wtorek/czwartek/sobota), liczby ułożone tak, by łatwo liczyć ręcznie
FAKE = [
    (1, "2024-01-02", [1, 2, 3, 4, 5, 6]),
    (2, "2024-01-04", [1, 2, 3, 10, 20, 30]),
    (3, "2024-01-06", [1, 2, 11, 21, 31, 41]),
    (4, "2024-01-09", [1, 12, 22, 32, 42, 49]),
    (5, "2024-01-11", [7, 8, 9, 13, 14, 15]),
]


@pytest.fixture
def fake_rows():
    return [["draw_id", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6"]] + [[i, d, *n] for i, d, n in FAKE]


@pytest.fixture
def fake_draws(fake_rows):
    return normalize_rows(fake_rows).draws


def to_csv_text(rows, sep=","):
    return "\n".join(sep.join("" if v is None else str(v) for v in r) for r in rows) + "\n"
