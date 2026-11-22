"""Warstwa usług wspólna dla API (FastAPI) i generatora plików statycznych (web/data).

Nie zawiera logiki statystycznej ani losującej — tylko wywołuje moduły z src/ i zamienia
wyniki na struktury gotowe do JSON.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from src import filters as flt, generator, statistics_engine as se
from src.data_loader import _typed, load_canonical_csv

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "lotto_normalized.csv"
NUM_COLS = generator.NUM_COLS
RECENT_DRAWS = 100          # okno „formy” liczby (ostatnie N losowań)
TOP = 10


def draw_to_dict(row) -> dict:
    return {
        "draw_id": int(row.draw_id),
        "draw_date": row.draw_date.date().isoformat(),
        "numbers": [int(getattr(row, c)) for c in NUM_COLS],
    }


def _tier(rank: int) -> str:
    """Klasa postaci w stylu gier: ranking 1–49 wg liczby wystąpień."""
    if rank <= 5:
        return "legenda"
    if rank <= 15:
        return "epicka"
    if rank <= 34:
        return "rzadka"
    if rank <= 44:
        return "zwykła"
    return "underdog"


@dataclass
class LottoService:
    draws: pd.DataFrame

    def __post_init__(self):
        self.draws = _typed(self.draws)   # daty jako datetime64, liczby jako int, porządek chronologiczny

    @classmethod
    def from_csv(cls, path: str | Path = DB_PATH) -> "LottoService":
        return cls(load_canonical_csv(path))

    # ------------------------------------------------------------ cache
    @cached_property
    def history(self) -> set[tuple[int, ...]]:
        return generator.history_set(self.draws)

    @cached_property
    def stats(self) -> dict:
        return self.build_stats()

    @cached_property
    def filter_ctx(self) -> flt.FilterContext:
        return flt.FilterContext(self.draws)

    @cached_property
    def filters_info(self) -> dict:
        ctx = self.filter_ctx
        return {
            "total_combos": flt.TOTAL_COMBOS,
            "sample_size": flt.SAMPLE_SIZE,
            "similar_default": flt.SIMILAR_DEFAULT,
            "context": {"hot": ctx.hot, "cold": ctx.cold, "last_draw": sorted(ctx.last_draw),
                        "recent_window": flt.RECENT_WINDOW},
            "note": "Filtry zmniejszają pulę kombinacji, ale nie zwiększają szansy na wygraną. "
                    "Gdy % zostających kombinacji ≈ % losowań z historii, które przeszłyby filtr, "
                    "filtr nie ma mocy przewidywania.",
            "filters": flt.describe(ctx),
        }

    def active_filters(self, keys: list[str] | None, similar_min: int = flt.SIMILAR_DEFAULT) -> flt.ActiveFilters:
        return flt.ActiveFilters(self.filter_ctx, list(keys or []), similar_min)

    def filter_estimate(self, keys: list[str] | None, similar_min: int = flt.SIMILAR_DEFAULT) -> dict:
        af = self.active_filters(keys, similar_min)
        return {"filters": af.keys, "similar_min": af.similar_min, **af.estimate()}

    # ------------------------------------------------------------ meta
    def meta(self) -> dict:
        d = self.draws
        if d.empty:
            return {"draws": 0}
        ids = set(int(x) for x in d["draw_id"])
        full = set(range(1, max(ids) + 1))
        missing = sorted(full - ids)
        return {
            "draws": int(len(d)),
            "first_date": d["draw_date"].min().date().isoformat(),
            "last_date": d["draw_date"].max().date().isoformat(),
            "first_id": int(min(ids)),
            "last_id": int(max(ids)),
            "missing_ids": _ranges(missing),
            "generator_version": generator.VERSION,
            "disclaimer": se.DISCLAIMER,
        }

    # ------------------------------------------------------------ losowania
    def filter(self, *, year: int | None = None, date_from: dt.date | None = None,
               date_to: dt.date | None = None) -> pd.DataFrame:
        d = self.draws
        if year is not None:
            d = d[d["draw_date"].dt.year == year]
        if date_from is not None:
            d = d[d["draw_date"] >= pd.Timestamp(date_from)]
        if date_to is not None:
            d = d[d["draw_date"] <= pd.Timestamp(date_to)]
        return d

    def latest(self) -> dict | None:
        if self.draws.empty:
            return None
        return draw_to_dict(next(self.draws.tail(1).itertuples()))

    def by_id(self, draw_id: int) -> dict | None:
        m = self.draws[self.draws["draw_id"] == draw_id]
        return draw_to_dict(next(m.itertuples())) if len(m) else None

    # ------------------------------------------------------------ statystyki
    def build_stats(self, draws: pd.DataFrame | None = None) -> dict:
        d = self.draws if draws is None else draws
        st = se.number_stats(d)
        recent = se.number_stats(d.tail(RECENT_DRAWS))
        recent_cnt = dict(zip(recent["liczba"], recent["wystąpienia"]))
        expected_recent = min(len(d), RECENT_DRAWS) * se.PICK / 49

        decades = sorted({(y // 10) * 10 for y in d["draw_date"].dt.year}) if len(d) else []
        dec_counts: dict[int, dict[int, float]] = {}
        for dec in decades:
            part = d[(d["draw_date"].dt.year // 10) * 10 == dec]
            c = generator.frequencies(part)
            # wystąpienia na 100 losowań w dekadzie (porównywalne między dekadami)
            dec_counts[dec] = {n: round(100 * int(c[n]) / len(part), 2) for n in range(1, 50)}

        numbers = []
        for r in st.to_dict("records"):
            n = int(r["liczba"])
            rank = int(r["ranking"])
            rc = int(recent_cnt.get(n, 0))
            last = r["ostatnie wystąpienie"]
            since = r["losowań od ostatniego"]
            numbers.append({
                "number": n,
                "count": int(r["wystąpienia"]),
                "percent": float(r["% losowań"]),
                "expected": float(r["oczekiwane"]),
                "deviation": float(r["odchylenie"]),
                "deviation_pct": float(r["odchylenie %"]),
                "rank": rank,
                "tier": _tier(rank),
                "last_date": last.isoformat() if last else None,
                "draws_since": None if since is None or pd.isna(since) else int(since),
                "recent_count": rc,
                "recent_form": round(rc - expected_recent, 2),
                "per_decade": [dec_counts[dec][n] for dec in decades],
            })
        by_count = sorted(numbers, key=lambda x: (-x["count"], x["number"]))
        by_since = sorted(numbers, key=lambda x: (-(x["draws_since"] if x["draws_since"] is not None else 10**9),
                                                  x["number"]))
        by_form = sorted(numbers, key=lambda x: (-x["recent_count"], x["number"]))
        chi = se.uniformity_test(st)
        return {
            "meta": self.meta() if draws is None else {"draws": int(len(d))},
            "recent_window": RECENT_DRAWS,
            "decades": decades,
            "numbers": numbers,
            "most_frequent": [x["number"] for x in by_count[:TOP]],
            "least_frequent": [x["number"] for x in by_count[::-1][:TOP]],
            "hot_recent": [x["number"] for x in by_form[:TOP]],
            "cold_recent": [x["number"] for x in by_form[::-1][:TOP]],
            "longest_absent": [x["number"] for x in by_since[:TOP]],
            "uniformity": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in chi.items()},
            "latest": self.latest() if draws is None else None,
        }

    # ------------------------------------------------------------ generator
    def losuj(self, strength: float = 1.0, count: int = 1, seed: int | None = None,
              filters: list[str] | None = None, similar_min: int = flt.SIMILAR_DEFAULT) -> list[dict]:
        rng = np.random.default_rng(seed)
        af = self.active_filters(filters, similar_min) if filters else None
        out = []
        for _ in range(count):
            r = generator.losuj6(self.draws, strength=strength, rng=rng, history=self.history, filters=af)
            out.append({
                "numbers": list(r.numbers),
                "attempts": r.attempts,
                "rejected_history": r.rejected_history,
                "strength_used": r.strength_used,
                "frequencies": {str(k): v for k, v in r.frequencies.items()},
                "weights_pct": {str(k): v for k, v in r.weights.items()},
                "never_drawn_before": tuple(r.numbers) not in self.history,
                "has_triple": generator.has_triple(r.numbers),
                "rejected_filters": r.rejected_filters,
            })
        return out


def _ranges(ids: list[int]) -> list[list[int]]:
    """[4356, 4357, …, 4476] → [[4356, 4476]]."""
    out: list[list[int]] = []
    for i in ids:
        if out and out[-1][1] == i - 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out
