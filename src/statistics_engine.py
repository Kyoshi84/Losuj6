"""Silnik statystyczny. Przyjmuje wyłącznie zwalidowany DataFrame w schemacie kanonicznym.

Nie zna ani interfejsu, ani źródła danych. Wszystkie funkcje są czyste (bez efektów ubocznych).
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

NUM_COLS = ["n1", "n2", "n3", "n4", "n5", "n6"]
NUMBERS = list(range(1, 50))
PICK = 6
LOW_SAMPLE_DRAWS = 20  # poniżej tylu losowań oznaczamy próbę jako ograniczoną

DISCLAIMER = (
    "Historyczne częstości NIE są prognozą. Przy prawidłowym losowaniu każda liczba od 1 do 49 ma "
    "taką samą szansę wypadnięcia w następnym losowaniu, niezależnie od wcześniejszych wyników."
)


# ---------------------------------------------------------------- okresy
def one_month_back(day: dt.date) -> dt.date:
    """Ta sama data miesiąc kalendarzowy wcześniej (z przycięciem do ostatniego dnia miesiąca)."""
    year, month = (day.year, day.month - 1) if day.month > 1 else (day.year - 1, 12)
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date

    def label(self) -> str:
        return f"{self.start.isoformat()} – {self.end.isoformat()}"


def last_month_period(today: dt.date | None = None) -> Period:
    """Okres „ostatni miesiąc": od tej samej daty miesiąc wcześniej do dziś włącznie."""
    today = today or dt.date.today()
    return Period(one_month_back(today), today)


def filter_period(draws: pd.DataFrame, period: Period | None) -> pd.DataFrame:
    if period is None or draws.empty:
        return draws.copy()
    d = pd.to_datetime(draws["draw_date"])
    mask = (d >= pd.Timestamp(period.start)) & (d <= pd.Timestamp(period.end))
    return draws.loc[mask].reset_index(drop=True)


@dataclass
class PeriodInfo:
    n_draws: int
    limited_sample: bool
    partial_coverage: bool
    messages: list[str]


def describe_period(draws: pd.DataFrame, period: Period | None) -> PeriodInfo:
    """Informacje ostrzegawcze: mała próba, dane nie pokrywają całego okresu, brak losowań."""
    msgs: list[str] = []
    if period is None:
        sub = draws
    else:
        sub = filter_period(draws, period)
    n = len(sub)
    partial = False
    if draws.empty:
        msgs.append("Baza jest pusta — brak danych do analizy.")
        return PeriodInfo(0, True, True, msgs)
    if period is not None:
        dmin, dmax = pd.to_datetime(draws["draw_date"]).min().date(), pd.to_datetime(draws["draw_date"]).max().date()
        if dmax < period.start:
            msgs.append(f"Brak losowań w okresie {period.label()}: dane kończą się {dmax}.")
            partial = True
        elif dmin > period.start or dmax < period.end:
            msgs.append(f"Dane obejmują {dmin} – {dmax}, czyli nie cały wybrany okres ({period.label()}).")
            partial = True
    if n == 0 and not msgs:
        msgs.append("W wybranym okresie nie ma żadnych losowań.")
    limited = 0 < n < LOW_SAMPLE_DRAWS
    if limited:
        msgs.append(f"Ograniczona próba: tylko {n} losowań — różnice częstości mogą być przypadkowe.")
    return PeriodInfo(n, limited or n == 0, partial, msgs)


# ---------------------------------------------------------------- statystyki liczb
def validate_sum(draws: pd.DataFrame, stats: pd.DataFrame) -> bool:
    """Suma wystąpień wszystkich liczb musi równać się 6 × liczba losowań."""
    return int(stats["wystąpienia"].sum()) == PICK * len(draws)


def number_stats(draws: pd.DataFrame) -> pd.DataFrame:
    """Tabela 49 wierszy ze statystykami dla przekazanego zbioru losowań (całość lub okres)."""
    n = len(draws)
    expected = n * PICK / len(NUMBERS)
    rows = []
    if n:
        d = pd.to_datetime(draws["draw_date"]).reset_index(drop=True)
        mat = draws[NUM_COLS].to_numpy()
    for k in NUMBERS:
        if n:
            hit = (mat == k).any(axis=1)
            cnt = int(hit.sum())
            idx = np.flatnonzero(hit)
            last_date = d.iloc[idx[-1]].date() if cnt else None
            since = int(n - 1 - idx[-1]) if cnt else None
        else:
            cnt, last_date, since = 0, None, None
        rows.append({
            "liczba": k,
            "wystąpienia": cnt,
            "% losowań": round(100 * cnt / n, 2) if n else 0.0,
            "na 100 losowań": round(100 * cnt / n, 2) if n else 0.0,
            "ostatnie wystąpienie": last_date,
            "losowań od ostatniego": since,
            "oczekiwane": round(expected, 2),
            "odchylenie": round(cnt - expected, 2),
            "odchylenie %": round(100 * (cnt - expected) / expected, 1) if expected else 0.0,
        })
    stats = pd.DataFrame(rows)
    stats["ranking"] = stats["wystąpienia"].rank(method="min", ascending=False).astype(int)
    tie = stats.groupby("wystąpienia")["liczba"].transform("count") > 1
    stats["remis"] = np.where(tie, "tak", "")
    return stats


def mean_frequency(draws: pd.DataFrame) -> float:
    """Średnia liczba wystąpień na jedną liczbę (oczekiwana przy równomiernym losowaniu)."""
    return len(draws) * PICK / len(NUMBERS)


# ---------------------------------------------------------------- rankingi
def top_n(stats: pd.DataFrame, n: int = 10, most: bool = True) -> pd.DataFrame:
    """TOP n najczęstszych / najrzadszych. Remisy na granicy NIE są rozstrzygane arbitralnie:
    zwracane są wszystkie liczby z wynikiem równym ostatniemu miejscu (wierszy może być > n)."""
    if stats.empty:
        return stats
    ordered = stats.sort_values(["wystąpienia", "liczba"], ascending=[not most, True])
    cutoff = ordered["wystąpienia"].iloc[min(n, len(ordered)) - 1]
    sel = ordered[ordered["wystąpienia"] >= cutoff] if most else ordered[ordered["wystąpienia"] <= cutoff]
    out = sel.copy()
    out["remis na granicy"] = np.where(out["wystąpienia"] == cutoff, np.where(
        (out["wystąpienia"] == cutoff).sum() > 1, "tak", ""), "")
    return out.reset_index(drop=True)


def never_drawn(stats: pd.DataFrame) -> pd.DataFrame:
    return stats[stats["wystąpienia"] == 0][["liczba"]].reset_index(drop=True)


def longest_absent(stats: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Liczby, które wystąpiły najdawniej. Liczby bez żadnego wystąpienia w zbiorze są na początku."""
    s = stats.copy()
    s["_k"] = s["losowań od ostatniego"].fillna(10**9)
    s = s.sort_values(["_k", "liczba"], ascending=[False, True]).drop(columns="_k")
    return s.head(n).reset_index(drop=True)


def compare_periods(stats_all: pd.DataFrame, stats_period: pd.DataFrame) -> pd.DataFrame:
    """Porównanie częstości w całej historii i w okresie + zmiana pozycji w rankingu."""
    a = stats_all.set_index("liczba")
    p = stats_period.set_index("liczba")
    out = pd.DataFrame({
        "liczba": a.index,
        "wystąpienia (całość)": a["wystąpienia"].values,
        "% losowań (całość)": a["% losowań"].values,
        "wystąpienia (okres)": p["wystąpienia"].values,
        "% losowań (okres)": p["% losowań"].values,
        "ranking (całość)": a["ranking"].values,
        "ranking (okres)": p["ranking"].values,
    })
    out["różnica % (pkt proc.)"] = (out["% losowań (okres)"] - out["% losowań (całość)"]).round(2)
    # dodatnia zmiana = liczba awansowała w rankingu okresu względem całości
    out["zmiana pozycji"] = out["ranking (całość)"] - out["ranking (okres)"]
    return out


def biggest_movers(cmp: pd.DataFrame, n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    risers = cmp.sort_values(["zmiana pozycji", "liczba"], ascending=[False, True]).head(n)
    fallers = cmp.sort_values(["zmiana pozycji", "liczba"], ascending=[True, True]).head(n)
    return risers.reset_index(drop=True), fallers.reset_index(drop=True)


# ---------------------------------------------------------------- test zgodności z rozkładem równomiernym
def uniformity_test(stats: pd.DataFrame) -> dict[str, float | int | None]:
    """Test χ² zgodności z rozkładem równomiernym. p-value wysokie = brak śladu nierównomierności."""
    n = int(stats["wystąpienia"].sum())
    if n == 0:
        return {"chi2": None, "p": None, "df": len(NUMBERS) - 1}
    from scipy.stats import chisquare

    res = chisquare(stats["wystąpienia"].to_numpy())
    return {"chi2": float(res.statistic), "p": float(res.pvalue), "df": len(NUMBERS) - 1}
