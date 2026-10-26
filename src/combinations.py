"""Statystyki kombinacji liczb: pary (k=2) i trójki (k=3).

Moduł jest niezależny od interfejsu i źródła danych; przyjmuje zwalidowany DataFrame
(schemat kanoniczny: draw_date, n1..n6). Liczenie jest wektorowe (kod kombinacji → bincount).
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

NUM_COLS = ["n1", "n2", "n3", "n4", "n5", "n6"]
PICK = 6
MAX_NUM = 49
BASE = 50  # podstawa kodowania kombinacji (liczby 1..49 < 50)
KIND = {2: "para", 3: "trójka"}

DISCLAIMER = (
    "Częste kombinacje z przeszłości NIE zwiększają szans na ich powtórkę. Przy prawidłowym losowaniu "
    "każda para i każda trójka ma w następnym losowaniu dokładnie takie samo prawdopodobieństwo."
)


def expected_per_draw(k: int) -> float:
    """Prawdopodobieństwo, że konkretna k-elementowa kombinacja jest w jednym losowaniu 6 z 49."""
    return math.comb(MAX_NUM - k, PICK - k) / math.comb(MAX_NUM, PICK)


def total_combinations(k: int) -> int:
    return math.comb(MAX_NUM, k)


def _decode(code: int, k: int) -> tuple[int, ...]:
    out = []
    for _ in range(k):
        out.append(code % BASE)
        code //= BASE
    return tuple(reversed(out))


def _codes(mat: np.ndarray, k: int) -> np.ndarray:
    """mat: (n, 6) posortowane wierszami → (n, C(6,k)) kody kombinacji."""
    cols = []
    for idx in itertools.combinations(range(PICK), k):
        code = np.zeros(len(mat), dtype=np.int64)
        for j in idx:
            code = code * BASE + mat[:, j]
        cols.append(code)
    return np.stack(cols, axis=1) if len(mat) else np.empty((0, math.comb(PICK, k)), dtype=np.int64)


def label(combo: tuple[int, ...]) -> str:
    return " – ".join(f"{x:02d}" for x in combo)


def combo_stats(draws: pd.DataFrame, k: int) -> pd.DataFrame:
    """Statystyki wszystkich k-elementowych kombinacji, które wystąpiły choć raz (posortowane malejąco).

    Kolumny: kombinacja, liczby, wystąpienia, % losowań, oczekiwane, odchylenie, ostatnie wystąpienie,
    losowań od ostatniego, ranking (remisy = ta sama pozycja), remis. Kombinacje bez wystąpień nie są
    wypisywane (dla trójek to ~18 tys. wierszy); ich liczbę podaje `never_drawn_count`.
    """
    if k not in KIND:
        raise ValueError("Obsługiwane są tylko pary (k=2) i trójki (k=3).")
    cols = ["kombinacja", "liczby", "wystąpienia", "% losowań", "oczekiwane", "odchylenie",
            "ostatnie wystąpienie", "losowań od ostatniego", "ranking", "remis"]
    n = len(draws)
    if n == 0:
        return pd.DataFrame(columns=cols)
    mat = np.sort(draws[NUM_COLS].to_numpy(dtype=np.int64), axis=1)
    codes = _codes(mat, k)
    per_draw = codes.shape[1]
    flat = codes.ravel()
    draw_idx = np.repeat(np.arange(n), per_draw)
    uniq, counts = np.unique(flat, return_counts=True)
    # ostatni indeks losowania dla każdej kombinacji
    order = np.argsort(flat, kind="stable")
    sorted_codes, sorted_idx = flat[order], draw_idx[order]
    last_pos = np.searchsorted(sorted_codes, uniq, side="right") - 1
    last_idx = sorted_idx[last_pos]
    dates = pd.to_datetime(draws["draw_date"]).reset_index(drop=True)
    exp = n * expected_per_draw(k)
    df = pd.DataFrame({
        "liczby": [_decode(int(c), k) for c in uniq],
        "wystąpienia": counts.astype(int),
        "ostatnie wystąpienie": [dates.iloc[i].date() for i in last_idx],
        "losowań od ostatniego": (n - 1 - last_idx).astype(int),
    })
    df["kombinacja"] = df["liczby"].map(label)
    df["% losowań"] = (100 * df["wystąpienia"] / n).round(2)
    df["oczekiwane"] = round(exp, 2)
    df["odchylenie"] = (df["wystąpienia"] - exp).round(2)
    df = df.sort_values(["wystąpienia", "liczby"], ascending=[False, True]).reset_index(drop=True)
    df["ranking"] = df["wystąpienia"].rank(method="min", ascending=False).astype(int)
    df["remis"] = np.where(df.groupby("wystąpienia")["liczby"].transform("count") > 1, "tak", "")
    return df[cols]


def never_drawn_count(stats: pd.DataFrame, k: int) -> int:
    """Ile możliwych kombinacji nie padło ani razu (w analizowanym zbiorze)."""
    return total_combinations(k) - len(stats)


@dataclass
class TopResult:
    table: pd.DataFrame
    boundary_count: int | None
    ties_at_boundary: int
    truncated: bool


def top_combos(stats: pd.DataFrame, n: int = 10, max_rows: int = 50) -> TopResult:
    """TOP n najczęstszych kombinacji. Remisu na granicy NIE rozstrzygamy arbitralnie: zwracamy wszystkie
    kombinacje z wynikiem równym n-tej (do limitu `max_rows` dla czytelności, o czym informuje `truncated`)."""
    if stats.empty:
        return TopResult(stats, None, 0, False)
    cutoff = int(stats["wystąpienia"].iloc[min(n, len(stats)) - 1])
    sel = stats[stats["wystąpienia"] >= cutoff]
    ties = int((sel["wystąpienia"] == cutoff).sum())
    truncated = len(sel) > max_rows
    return TopResult(sel.head(max_rows).reset_index(drop=True), cutoff, ties if ties > 1 else 0, truncated)


def lookup(stats: pd.DataFrame, combo: tuple[int, ...]) -> pd.Series | None:
    """Wiersz statystyk dla podanej kombinacji lub None, gdy nigdy nie padła."""
    key = tuple(sorted(combo))
    hit = stats[stats["liczby"] == key]
    return hit.iloc[0] if len(hit) else None


def combo_history(draws: pd.DataFrame, combo: tuple[int, ...]) -> pd.DataFrame:
    """Losowania, w których padła dana kombinacja (data, numer, liczby)."""
    want = set(combo)
    mask = draws[NUM_COLS].apply(lambda r: want <= set(r), axis=1) if len(draws) else pd.Series([], dtype=bool)
    out = draws.loc[mask, ["draw_id", "draw_date", *NUM_COLS]].copy()
    return out.reset_index(drop=True)


def yearly_counts(draws: pd.DataFrame, combo: tuple[int, ...]) -> pd.DataFrame:
    """Trend: liczba wystąpień kombinacji w każdym roku wraz z oczekiwaniem (przy równomiernym losowaniu).
    Rok z niepełnymi danymi ma mniej losowań, dlatego podajemy też liczbę losowań w roku."""
    if draws.empty:
        return pd.DataFrame(columns=["rok", "losowań", "wystąpienia", "oczekiwane"])
    years = pd.to_datetime(draws["draw_date"]).dt.year
    hist_years = pd.to_datetime(combo_history(draws, combo)["draw_date"]).dt.year
    p = expected_per_draw(len(combo))
    rows = [{"rok": int(y), "losowań": int((years == y).sum()), "wystąpienia": int((hist_years == y).sum())}
            for y in sorted(years.unique())]
    out = pd.DataFrame(rows)
    out["oczekiwane"] = (out["losowań"] * p).round(2)
    return out


def null_benchmark(n_draws: int, k: int, sims: int = 300, seed: int = 12345,
                   observed: int | None = None) -> dict[str, float | None]:
    """Ile razy NAJCZĘSTSZA kombinacja pada w czysto losowych danych o tej samej liczbie losowań.

    Odpowiada na pytanie „czy lider rankingu jest zaskakujący?". Symulacja jest deterministyczna (ziarno).
    Zwraca średnią oraz zakres 5–95 percentyla maksimum z `sims` symulacji. Gdy podano `observed`
    (liczba wystąpień lidera w prawdziwych danych), zwraca też `p`: odsetek symulacji, w których lider
    był co najmniej tak częsty. Wysokie p (np. > 0,05) = wynik mieści się w normie losowej.
    """
    if n_draws <= 0:
        return {"średnia": 0.0, "p05": 0.0, "p95": 0.0, "symulacji": 0, "p": None}
    rng = np.random.default_rng(seed)
    maxima = np.empty(sims)
    for s in range(sims):
        draws = np.sort(np.argpartition(rng.random((n_draws, MAX_NUM)), PICK, axis=1)[:, :PICK] + 1, axis=1)
        _, counts = np.unique(_codes(draws, k).ravel(), return_counts=True)
        maxima[s] = counts.max()
    p = None if observed is None else float((maxima >= observed).mean())
    return {"średnia": float(maxima.mean()), "p05": float(np.percentile(maxima, 5)),
            "p95": float(np.percentile(maxima, 95)), "symulacji": sims, "p": p}
