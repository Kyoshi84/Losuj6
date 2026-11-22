"""Generator „Losuj 6” — losowanie 6 liczb z 49 z regułami.

Reguły:
1. Wagi liczb rosną z liczbą wystąpień w historii (statystyki najczęściej padających numerów).
   Parametr ``strength`` steruje wpływem: 0 = losowanie równomierne, 1 = waga ∝ (wystąpienia + 1),
   2 = waga ∝ (wystąpienia + 1)², itd.
2. Wynik nie może być kombinacją, która już padła w historii losowań.
3. Wynik nie może zawierać 3 kolejnych liczb (np. jeśli wylosowano 1 i 2, to 3 jest wykluczona;
   tak samo 0 przy parze 2–3 czy 2 przy parze 1–3).

Moduł jest czysty (bez interfejsu); przyjmuje DataFrame w schemacie kanonicznym (n1..n6).
Uwaga: reguły zmieniają, KTÓRE kombinacje są wybierane, ale nie zmieniają szansy na wygraną —
każda kombinacja 6 z 49 ma w prawidłowym losowaniu takie samo prawdopodobieństwo.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from .filters import ActiveFilters

VERSION = "0.1"
BUTTON_LABEL = f"Losuj 6 v {VERSION}"
NUM_COLS = ["n1", "n2", "n3", "n4", "n5", "n6"]
MAX_NUM = 49
PICK = 6
MAX_ATTEMPTS = 10_000
FLATTEN_EVERY = 100  # co tyle odrzuceń wpływ statystyk spada o połowę
FILTERED_MAX_ATTEMPTS = 300_000   # z filtrami pula bywa bardzo mała (np. „bez podobnych” od 4 wspólnych)
FILTER_FLATTEN_EVERY = 2_000      # co tyle odrzuceń przez filtry wpływ statystyk spada o połowę
TIME_BUDGET_S = 15.0              # limit czasu jednego losowania z filtrami


class GeneratorError(RuntimeError):
    pass


@dataclass
class DrawResult:
    numbers: tuple[int, ...]
    attempts: int                       # ile pełnych prób było potrzebnych
    rejected_history: int               # ile prób odrzucono, bo kombinacja była w historii
    frequencies: dict[int, int] = field(default_factory=dict)  # wystąpienia wylosowanych liczb
    weights: dict[int, float] = field(default_factory=dict)    # prawdopodobieństwo bazowe liczby (%)
    strength_used: float = 1.0          # wpływ statystyk faktycznie użyty (może być spłaszczony)
    rejected_filters: dict[str, int] = field(default_factory=dict)  # odrzucenia przez filtry (klucz → ile)


def frequencies(draws: pd.DataFrame) -> np.ndarray:
    """Liczba wystąpień każdej liczby; indeks 0 nieużywany, 1..49 = liczby."""
    counts = np.zeros(MAX_NUM + 1, dtype=np.int64)
    if draws is not None and not draws.empty:
        vals = draws[NUM_COLS].to_numpy().ravel().astype(int)
        counts += np.bincount(vals, minlength=MAX_NUM + 1)[: MAX_NUM + 1]
    return counts


def number_weights(counts: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Wagi 1..49 (indeks 0 = 0). +1 sprawia, że liczba bez wystąpień nadal może paść."""
    if strength < 0:
        raise ValueError("strength musi być ≥ 0")
    w = (counts.astype(float) + 1.0) ** strength
    w[0] = 0.0
    return w


def history_set(draws: pd.DataFrame) -> set[tuple[int, ...]]:
    """Zbiór posortowanych kombinacji, które już padły."""
    if draws is None or draws.empty:
        return set()
    mat = np.sort(draws[NUM_COLS].to_numpy().astype(int), axis=1)
    return {tuple(int(x) for x in row) for row in mat}


def makes_triple(picked: set[int], n: int) -> bool:
    """Czy dodanie n do picked tworzy 3 kolejne liczby."""
    return ((n - 1 in picked and n - 2 in picked)
            or (n - 1 in picked and n + 1 in picked)
            or (n + 1 in picked and n + 2 in picked))


def has_triple(combo) -> bool:
    s = set(combo)
    return any(n in s and n + 1 in s and n + 2 in s for n in s)


def _one_pass(weights: np.ndarray, rng: np.random.Generator,
              filters: "ActiveFilters | None" = None) -> tuple[int, ...]:
    picked: set[int] = set()
    order: list[int] = []
    weighted = filters is not None and filters.has_weights
    for _ in range(PICK):
        cand = np.array([n for n in range(1, MAX_NUM + 1) if n not in picked and not makes_triple(picked, n)])
        p = weights[cand]
        if weighted:
            p = p * filters.pick_factor(cand, order)
        p = p / p.sum()
        n = int(rng.choice(cand, p=p))
        picked.add(n)
        order.append(n)
    return tuple(sorted(picked))


def losuj6(draws: pd.DataFrame | None = None, *, stats_draws: pd.DataFrame | None = None,
           strength: float = 1.0, rng: np.random.Generator | None = None,
           history: set[tuple[int, ...]] | None = None, max_attempts: int | None = None,
           filters: "ActiveFilters | None" = None, time_budget: float = TIME_BUDGET_S) -> DrawResult:
    """Losuje 6 z 49 zgodnie z regułami modułu.

    draws        — pełna historia (do wykluczania kombinacji, które padły).
    stats_draws  — losowania, z których liczone są statystyki (domyślnie = draws).
    strength     — wpływ statystyk (0 = brak).
    filters      — opcjonalne filtry trybu ekspert (src/filters.py): reguły odrzucają gotowe kombinacje,
                   wagi (pary, trójki) zmieniają wybór kolejnych liczb.
    """
    rng = rng or np.random.default_rng()
    hist = history if history is not None else history_set(draws)
    counts = frequencies(stats_draws if stats_draws is not None else draws)
    w = number_weights(counts, strength)
    active = filters if filters else None
    if max_attempts is None:
        max_attempts = FILTERED_MAX_ATTEMPTS if active else MAX_ATTEMPTS
    deadline = time.monotonic() + time_budget if active else None
    rejected = 0
    rejected_f: dict[str, int] = {}
    n_filtered = 0
    for attempt in range(1, max_attempts + 1):
        combo = _one_pass(w, rng, active)
        if combo in hist:
            rejected += 1
            if rejected % FLATTEN_EVERY == 0:      # skrajne wagi ciągle dają kombinację z historii
                strength /= 2                      # → stopniowo spłaszczamy rozkład
                w = number_weights(counts, strength)
            continue
        if active:
            why = active.rejects(combo)
            if why:
                rejected_f[why] = rejected_f.get(why, 0) + 1
                n_filtered += 1
                if n_filtered % FILTER_FLATTEN_EVERY == 0:
                    strength /= 2
                    w = number_weights(counts, strength)
                if n_filtered % 500 == 0 and time.monotonic() > deadline:
                    raise GeneratorError(
                        f"Filtry są zbyt restrykcyjne: w {time_budget:.0f} s nie znaleziono kombinacji "
                        f"({attempt} prób). Wyłącz któryś filtr.")
                continue
        base = 100 * w / w.sum()
        return DrawResult(combo, attempt, rejected,
                          frequencies={n: int(counts[n]) for n in combo},
                          weights={n: round(float(base[n]), 3) for n in combo},
                          strength_used=strength, rejected_filters=rejected_f)
    raise GeneratorError(f"Nie udało się wylosować nowej kombinacji w {max_attempts} próbach.")
