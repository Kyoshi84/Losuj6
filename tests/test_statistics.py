import datetime as dt
from collections import Counter

import pandas as pd

from conftest import FAKE
from src import statistics_engine as se


def test_czestosci_zgodne_z_liczeniem_recznym(fake_draws):
    stats = se.number_stats(fake_draws)
    manual = Counter(x for _, _, n in FAKE for x in n)
    assert len(stats) == 49
    for _, row in stats.iterrows():
        assert row["wystąpienia"] == manual.get(row["liczba"], 0)


def test_suma_wystapien_to_6_razy_losowania(fake_draws):
    stats = se.number_stats(fake_draws)
    assert stats["wystąpienia"].sum() == 6 * len(fake_draws) and se.validate_sum(fake_draws, stats)


def test_procenty_oczekiwane_i_odchylenie(fake_draws):
    s = se.number_stats(fake_draws).set_index("liczba")
    assert s.loc[1, "% losowań"] == 80.0 and s.loc[2, "wystąpienia"] == 3
    assert s.loc[1, "oczekiwane"] == round(5 * 6 / 49, 2)
    assert s.loc[1, "odchylenie"] == round(4 - 5 * 6 / 49, 2)


def test_ostatnie_wystapienie_i_losowania_od_ostatniego(fake_draws):
    s = se.number_stats(fake_draws).set_index("liczba")
    assert s.loc[1, "ostatnie wystąpienie"] == dt.date(2024, 1, 9) and s.loc[1, "losowań od ostatniego"] == 1
    assert s.loc[7, "losowań od ostatniego"] == 0
    assert pd.isna(s.loc[16, "ostatnie wystąpienie"]) and pd.isna(s.loc[16, "losowań od ostatniego"])


def test_ranking_z_remisami(fake_draws):
    s = se.number_stats(fake_draws).set_index("liczba")
    assert (s.loc[1, "ranking"], s.loc[2, "ranking"], s.loc[3, "ranking"]) == (1, 2, 3)
    assert s.loc[3, "remis"] == ""                                   # jedyna liczba z 2 wystąpieniami
    once = s[s["wystąpienia"] == 1]
    assert len(once) > 1 and (once["ranking"] == 4).all() and (once["remis"] == "tak").all()  # remis = ta sama pozycja


def test_top_n_nie_rozstrzyga_remisu_arbitralnie(fake_draws):
    s = se.number_stats(fake_draws)
    assert len(se.top_n(s, 3, most=True)) == 3                       # brak remisu na granicy
    top5 = se.top_n(s, 5, most=True)                                 # granica trafia w remis (wynik 1)
    assert len(top5) > 5 and (top5[top5["wystąpienia"] == 1]["remis na granicy"] == "tak").all()
    bottom = se.top_n(s, 10, most=False)
    assert (bottom["wystąpienia"] == 0).all() and len(bottom) >= 10


def test_liczby_niewystepujace_i_najdawniej(fake_draws):
    s = se.number_stats(fake_draws)
    assert 16 in se.never_drawn(s)["liczba"].tolist() and 1 not in se.never_drawn(s)["liczba"].tolist()
    assert se.longest_absent(s, 5)["losowań od ostatniego"].isna().all()   # niewystępujące na początku


def test_ostatni_miesiac_od_daty_a_nie_poprzedni_miesiac_kalendarzowy():
    p = se.last_month_period(dt.date(2024, 3, 31))
    assert (p.start, p.end) == (dt.date(2024, 2, 29), dt.date(2024, 3, 31))     # przycięcie do 29 lutego
    assert se.last_month_period(dt.date(2023, 3, 31)).start == dt.date(2023, 2, 28)
    assert se.last_month_period(dt.date(2024, 1, 15)).start == dt.date(2023, 12, 15)
    assert se.last_month_period(dt.date(2026, 10, 21)).start == dt.date(2026, 9, 21)


def test_filtr_okresu_wlacznie_z_granicami(fake_draws):
    sub = se.filter_period(fake_draws, se.Period(dt.date(2024, 1, 4), dt.date(2024, 1, 9)))
    assert list(sub["draw_id"]) == [2, 3, 4]


def test_pusty_zbior_danych():
    empty = pd.DataFrame({"draw_id": pd.Series(dtype="Int64"), "draw_date": pd.to_datetime([]), **{c: pd.Series(dtype=int) for c in se.NUM_COLS}})
    s = se.number_stats(empty)
    assert len(s) == 49 and s["wystąpienia"].sum() == 0 and se.validate_sum(empty, s)
    assert se.describe_period(empty, None).messages
    assert se.uniformity_test(s)["p"] is None


def test_brak_aktualnych_losowan(fake_draws):
    info = se.describe_period(fake_draws, se.last_month_period(dt.date(2026, 10, 21)))
    assert info.n_draws == 0 and info.partial_coverage and any("Brak losowań" in m for m in info.messages)


def test_ograniczona_proba_i_czesciowe_pokrycie(fake_draws):
    info = se.describe_period(fake_draws, se.Period(dt.date(2023, 12, 1), dt.date(2024, 1, 31)))
    assert info.limited_sample and info.partial_coverage and len(info.messages) == 2


def test_porownanie_okresow(fake_draws):
    sub = se.filter_period(fake_draws, se.Period(dt.date(2024, 1, 9), dt.date(2024, 1, 11)))
    cmp = se.compare_periods(se.number_stats(fake_draws), se.number_stats(sub))
    assert len(cmp) == 49 and cmp.loc[cmp["liczba"] == 7, "wystąpienia (okres)"].item() == 1
    up, down = se.biggest_movers(cmp, 3)
    assert up["zmiana pozycji"].iloc[0] >= down["zmiana pozycji"].iloc[0]
