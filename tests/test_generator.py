"""Testy generatora Losuj 6 (dane sztuczne)."""
import numpy as np
import pandas as pd

from src import generator as gen


def test_przycisk_i_wersja():
    assert gen.BUTTON_LABEL == "Losuj 6 v 0.1"


def test_makes_triple():
    assert gen.makes_triple({1, 2}, 3)
    assert gen.makes_triple({2, 3}, 1)
    assert gen.makes_triple({1, 3}, 2)
    assert not gen.makes_triple({1, 2}, 4)
    assert not gen.makes_triple({1, 3}, 5)


def test_wynik_spelnia_reguly(fake_draws):
    rng = np.random.default_rng(1)
    hist = gen.history_set(fake_draws)
    for _ in range(500):
        r = gen.losuj6(fake_draws, rng=rng)
        assert len(r.numbers) == 6 and len(set(r.numbers)) == 6
        assert all(1 <= n <= 49 for n in r.numbers)
        assert list(r.numbers) == sorted(r.numbers)
        assert not gen.has_triple(r.numbers)
        assert r.numbers not in hist


def test_pomija_kombinacje_z_historii():
    # przy silnym wpływie statystyk liczby 10,20,30,40,45,49 dominują — ta kombinacja jest w historii
    combo = [10, 20, 30, 40, 45, 49]
    draws = pd.DataFrame([dict(zip(gen.NUM_COLS, combo))] * 200)
    rng = np.random.default_rng(0)
    r = gen.losuj6(draws, strength=3.0, rng=rng)
    assert r.numbers != tuple(combo)
    assert r.rejected_history > 0


def test_statystyki_faworyzuja_czeste_liczby():
    draws = pd.DataFrame([dict(zip(gen.NUM_COLS, [5, 15, 25, 35, 41, 47]))] * 50
                         + [dict(zip(gen.NUM_COLS, [1, 3, 8, 12, 19, 22]))])
    rng = np.random.default_rng(2)
    hits = sum(5 in gen.losuj6(draws, rng=rng).numbers for _ in range(300))
    assert hits > 200          # bez statystyk ~37 (6/49 * 300)
    rng = np.random.default_rng(2)
    hits0 = sum(5 in gen.losuj6(draws, strength=0, rng=rng).numbers for _ in range(300))
    assert hits0 < 80


def test_pusta_baza():
    r = gen.losuj6(pd.DataFrame(columns=["draw_id", "draw_date", *gen.NUM_COLS]), rng=np.random.default_rng(3))
    assert len(r.numbers) == 6 and r.attempts == 1
