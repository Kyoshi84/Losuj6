"""Testy par i trójek. Dane SZTUCZNE (conftest.FAKE) — nie są prawdziwymi wynikami Lotto."""
import collections
import itertools
import math

import numpy as np
import pandas as pd
import pytest

from src import combinations as cb
from src.normalizer import normalize_rows


class _Stats:
    """Dostęp do wiersza po krotce liczb (krotki w indeksie pandas stają się MultiIndex, więc nie używamy .loc)."""

    def __init__(self, df):
        self.df = df

    def __getitem__(self, key):
        hit = self.df[self.df["liczby"] == key]
        assert len(hit) == 1, f"oczekiwano jednego wiersza dla {key}, jest {len(hit)}"
        return hit.iloc[0]


def stats(draws, k):
    return _Stats(cb.combo_stats(draws, k))


def test_liczby_par_i_trojek_zgodne_z_liczeniem_recznym(fake_draws):
    p = stats(fake_draws, 2)
    # (1,2) w losowaniach 1,2,3; (1,3) i (2,3) w 1,2; reszta po 1
    assert p[(1, 2)]["wystąpienia"] == 3
    assert p[(1, 3)]["wystąpienia"] == 2 and p[(2, 3)]["wystąpienia"] == 2
    t = stats(fake_draws, 3)
    assert t[(1, 2, 3)]["wystąpienia"] == 2
    assert t.df["wystąpienia"].max() == 2 and (t.df["wystąpienia"] == 2).sum() == 1


def test_suma_wystapien_to_C6k_razy_losowania(fake_draws):
    for k in (2, 3):
        assert cb.combo_stats(fake_draws, k)["wystąpienia"].sum() == math.comb(6, k) * len(fake_draws)


def test_oczekiwane_sumuja_sie_do_C6k():
    for k in (2, 3):
        assert cb.expected_per_draw(k) * cb.total_combinations(k) == pytest.approx(math.comb(6, k))


def test_ostatnie_wystapienie_i_losowania_od_ostatniego(fake_draws):
    row = stats(fake_draws, 2)[(1, 2)]
    assert str(row["ostatnie wystąpienie"]) == "2024-01-06" and row["losowań od ostatniego"] == 2
    row = stats(fake_draws, 2)[(7, 8)]
    assert row["losowań od ostatniego"] == 0


def test_ranking_i_remisy(fake_draws):
    p = stats(fake_draws, 2)
    assert p[(1, 2)]["ranking"] == 1 and p[(1, 2)]["remis"] == ""
    assert p[(1, 3)]["ranking"] == p[(2, 3)]["ranking"] == 2
    assert p[(1, 3)]["remis"] == p[(2, 3)]["remis"] == "tak"
    assert p[(7, 8)]["ranking"] > 2   # pojedyncze wystąpienia: dalsza, wspólna pozycja


def test_top_nie_rozstrzyga_remisu_arbitralnie(fake_draws):
    s = cb.combo_stats(fake_draws, 2)
    top1 = cb.top_combos(s, 1)
    assert len(top1.table) == 1 and top1.ties_at_boundary == 0
    top2 = cb.top_combos(s, 2)           # 2. miejsce dzielą (1,3) i (2,3) → oba muszą być pokazane
    assert len(top2.table) == 3 and top2.boundary_count == 2 and top2.ties_at_boundary == 2 and not top2.truncated
    assert cb.top_combos(s, 2, max_rows=2).truncated


def test_ile_kombinacji_nie_padlo(fake_draws):
    s = cb.combo_stats(fake_draws, 2)
    assert cb.never_drawn_count(s, 2) == 1176 - len(s) and cb.never_drawn_count(s, 2) > 0


def test_lookup_niezalezny_od_kolejnosci_i_brak_wyniku(fake_draws):
    s = cb.combo_stats(fake_draws, 2)
    assert cb.lookup(s, (2, 1))["wystąpienia"] == 3
    assert cb.lookup(s, (48, 49)) is None


def test_historia_i_trend_roczny(fake_draws):
    h = cb.combo_history(fake_draws, (1, 2))
    assert list(h["draw_id"]) == [1, 2, 3]
    y = cb.yearly_counts(fake_draws, (1, 2))
    assert y["wystąpienia"].sum() == 3 and y["losowań"].sum() == 5
    assert y["oczekiwane"].iloc[0] == pytest.approx(5 * cb.expected_per_draw(2), abs=0.01)
    assert cb.combo_history(fake_draws, (48, 49)).empty


def test_zgodnosc_z_naiwnym_liczeniem_na_losowych_danych():
    rng = np.random.default_rng(7)
    rows = [["draw_id", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6"]]
    for i in range(300):
        rows.append([i + 1, (pd.Timestamp("2020-01-01") + pd.Timedelta(days=3 * i)).strftime("%Y-%m-%d"),
                     *sorted(rng.choice(np.arange(1, 50), 6, replace=False).tolist())])
    draws = normalize_rows(rows).draws
    for k in (2, 3):
        naive, last = collections.Counter(), {}
        for i, r in enumerate(draws[cb.NUM_COLS].itertuples(index=False)):
            for c in itertools.combinations(sorted(r), k):
                naive[c] += 1; last[c] = i
        s = cb.combo_stats(draws, k)
        assert len(s) == len(naive)
        for r in s.itertuples():
            assert naive[r.liczby] == r.wystąpienia
            assert len(draws) - 1 - last[r.liczby] == r._8   # losowań od ostatniego


def test_pusty_zbior_i_zly_rodzaj(fake_draws):
    assert cb.combo_stats(fake_draws.iloc[0:0], 2).empty
    assert cb.top_combos(cb.combo_stats(fake_draws.iloc[0:0], 2)).table.empty
    with pytest.raises(ValueError):
        cb.combo_stats(fake_draws, 4)


def test_benchmark_losowy_jest_deterministyczny_i_zwraca_p():
    a = cb.null_benchmark(60, 2, sims=20, seed=1, observed=5)
    b = cb.null_benchmark(60, 2, sims=20, seed=1, observed=5)
    assert a == b and a["p05"] <= a["średnia"] <= a["p95"] and 0 <= a["p"] <= 1
    assert cb.null_benchmark(60, 2, sims=20, observed=0)["p"] == 1.0
    assert cb.null_benchmark(60, 2, sims=20, observed=10**6)["p"] == 0.0
    assert cb.null_benchmark(60, 2, sims=20)["p"] is None
    assert cb.null_benchmark(0, 2)["symulacji"] == 0
