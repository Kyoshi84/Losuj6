"""Filtry generatora „Losuj 6” (tryb ekspert).

Dwa rodzaje:
- **reguła** — odrzuca gotową kombinację, która nie spełnia warunku (np. suma poza 100–200),
- **waga** — zmienia prawdopodobieństwo wyboru kolejnej liczby w trakcie losowania (pary, trójki).

Uczciwa uwaga (widoczna też na stronie): filtry zmniejszają pulę kombinacji, z której losujemy,
ale NIE zwiększają szansy na wygraną — każda z 13 983 816 kombinacji ma tę samą szansę.
Dla każdej reguły liczymy dwie liczby: ile procent wszystkich kombinacji zostaje i ile procent
prawdziwych losowań z historii przeszłoby filtr. Gdy są równe, filtr nie ma żadnej mocy przewidywania.

Moduł jest czysty (bez interfejsu): przyjmuje DataFrame w schemacie kanonicznym.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
import pandas as pd

NUM_COLS = ["n1", "n2", "n3", "n4", "n5", "n6"]
TOTAL_COMBOS = math.comb(49, 6)
RECENT_WINDOW = 100
TOP = 10
SAMPLE_SIZE = 50_000
SAMPLE_SEED = 12345
SIMILAR_DEFAULT = 4


class FilterError(ValueError):
    """Niepoprawny wybór filtrów (nieznany filtr, filtry wzajemnie się wykluczające, zły parametr)."""


@dataclass(frozen=True)
class FilterInfo:
    key: str
    no: int
    name: str
    kind: str              # "reguła" | "waga"
    short: str             # jedno zdanie na przełącznik
    info: str              # pełny opis pod ikoną ⓘ
    excludes: tuple[str, ...] = ()


FILTERS: tuple[FilterInfo, ...] = (
    FilterInfo("pary", 1, "Pary często razem", "waga",
               "Premiuje liczby, które w historii często padały razem z już wylosowanymi.",
               "Przy wyborze każdej kolejnej liczby jej waga jest mnożona przez to, jak często padała w parze "
               "z liczbami już wybranymi (w stosunku do średniej). Rozrzut częstości par w historii jest taki, "
               "jakiego oczekuje się po czystym przypadku, więc to ciekawostka, a nie przewaga.",
               excludes=("podobne",)),
    FilterInfo("trojki", 2, "Trójki często razem", "waga",
               "Premiuje liczby, które w historii tworzyły trójki z już wylosowanymi.",
               "Jak filtr par, tylko dla trójek: waga kandydata rośnie, jeśli razem z dwiema już wybranymi "
               "liczbami często tworzył trójkę w historii. Trójek jest 18 424, a każda padła średnio kilka razy, "
               "więc różnice są w dużej mierze przypadkowe.",
               excludes=("podobne",)),
    FilterInfo("suma", 3, "Suma 100–200", "reguła",
               "Suma sześciu liczb musi być w przedziale 100–200.",
               "Odrzuca kombinacje o bardzo małej lub bardzo dużej sumie (np. 1-2-4-6-8-10). Średnia suma to 150."),
    FilterInfo("parzyste", 4, "Parzyste 2–4", "reguła",
               "Od 2 do 4 liczb parzystych (bez kuponów samych parzystych lub nieparzystych).",
               "Odrzuca układy 0, 1, 5 i 6 liczb parzystych."),
    FilterInfo("niskie", 5, "Niskie/wysokie 2–4", "reguła",
               "Od 2 do 4 liczb z zakresu 1–24, reszta z 25–49.",
               "Odrzuca kupony zbudowane prawie wyłącznie z małych albo z dużych liczb."),
    FilterInfo("dziesiatki", 6, "Max 3 z jednej dziesiątki", "reguła",
               "Najwyżej 3 liczby z tej samej dziesiątki (1–9, 10–19, …, 40–49).",
               "Odrzuca kupony skupione w jednej dziesiątce, np. 30-31-34-36-38-39."),
    FilterInfo("koncowki", 7, "Max 2 z tą samą końcówką", "reguła",
               "Najwyżej 2 liczby z tą samą ostatnią cyfrą (np. 7, 17, 27).",
               "Odrzuca kupony typu 3-13-23-33-…, w których wiele liczb kończy się tą samą cyfrą."),
    FilterInfo("kolejne", 8, "Max 1 para kolejnych", "reguła",
               "Najwyżej jedna para sąsiednich liczb (np. 14-15).",
               "Zaostrza stałą regułę generatora (bez 3 kolejnych liczb): dopuszcza tylko jedną parę sąsiadów."),
    FilterInfo("powtorki", 9, "Max 1 z ostatniego losowania", "reguła",
               "Najwyżej jedna liczba z ostatniego losowania w bazie.",
               "Odrzuca kupony, które powtarzają 2 lub więcej liczb z ostatniego losowania."),
    FilterInfo("podobne", 10, "Bez podobnych do historii", "reguła",
               "Odrzuca kombinacje, które mają co najmniej 4 (lub 5) liczby wspólne z dowolnym losowaniem z historii.",
               "Stała reguła generatora odrzuca tylko identyczne kombinacje. Ten filtr idzie dalej. "
               "Uwaga: przy progu 4 historia jest już tak gęsta, że zostaje bardzo mało kombinacji, "
               "a prawie każde nowe prawdziwe losowanie zostałoby odrzucone.",
               excludes=("pary", "trojki")),
    FilterInfo("goraco_zimno", 11, "Ogień i lód", "reguła",
               "Co najmniej 2 liczby z „ognia” (najczęstsze w ostatnich 100 losowaniach) i 1 z „lodu” (najdłużej nieobecne).",
               "Łączy dziesiątkę najgorętszych liczb z ostatnich 100 losowań z dziesiątką liczb, które najdłużej "
               "nie padły. Forma liczb w loterii nie przechodzi na kolejne losowania — to wybór stylu kuponu."),
    FilterInfo("popularne", 12, "Omijaj popularne kupony", "reguła",
               "Bez kuponów z samych dat (wszystkie liczby ≤ 31) i bez ciągów typu 5-10-15-20.",
               "Nie zwiększa szansy na trafienie, ale przy wygranej zmniejsza ryzyko dzielenia puli z innymi: "
               "bardzo wielu graczy wybiera daty urodzin i regularne ciągi. Odrzuca kupony, w których wszystkie "
               "liczby są ≤ 31, oraz kupony z co najmniej 4 liczbami w równych odstępach."),
)
BY_KEY = {f.key: f for f in FILTERS}


# ------------------------------------------------------------------ reguły (wektorowo: M ma kształt [n, 6], wiersze posortowane)
def _sum_ok(M):
    s = M.sum(1)
    return (s >= 100) & (s <= 200)


def _even_ok(M):
    e = (M % 2 == 0).sum(1)
    return (e >= 2) & (e <= 4)


def _low_ok(M):
    lo = (M <= 24).sum(1)
    return (lo >= 2) & (lo <= 4)


def _count_max(keys: np.ndarray, size: int) -> np.ndarray:
    """Maksymalna liczba powtórzeń wartości w każdym wierszu (wartości 0..size-1)."""
    onehot = np.zeros((keys.shape[0], size), dtype=np.int8)
    rows = np.repeat(np.arange(keys.shape[0]), keys.shape[1])
    np.add.at(onehot, (rows, keys.ravel()), 1)
    return onehot.max(1)


def _decades_ok(M):
    return _count_max(M // 10, 5) <= 3


def _endings_ok(M):
    return _count_max(M % 10, 10) <= 2


def _consecutive_ok(M):
    return (np.diff(M, axis=1) == 1).sum(1) <= 1


def _has_arith4(M) -> np.ndarray:
    """Czy w wierszu są ≥4 liczby w równych odstępach (ciąg arytmetyczny)."""
    out = np.zeros(M.shape[0], dtype=bool)
    present = np.zeros((M.shape[0], 50), dtype=bool)
    present[np.repeat(np.arange(M.shape[0]), 6), M.ravel()] = True
    for i, j in itertools.combinations(range(6), 2):
        a, b = M[:, i], M[:, j]
        step = b - a
        c, d = b + step, b + 2 * step
        ok_c = c <= 49
        ok_d = d <= 49
        hit = np.zeros(M.shape[0], dtype=bool)
        idx = np.flatnonzero(ok_d)
        hit[idx] = present[idx, c[idx]] & present[idx, d[idx]]
        out |= hit & ok_c
    return out


def _popular_ok(M):
    return (M[:, 5] > 31) & ~_has_arith4(M)


# ------------------------------------------------------------------ kontekst z historii
@dataclass
class FilterContext:
    """Dane z historii potrzebne filtrom. Budowane raz dla bazy (kosztowne części są leniwe)."""
    draws: pd.DataFrame

    def __post_init__(self):
        d = self.draws
        if not d.empty and not pd.api.types.is_datetime64_any_dtype(d["draw_date"]):
            d = d.assign(draw_date=pd.to_datetime(d["draw_date"]))
        self.draws = d.sort_values(["draw_date", "draw_id"], kind="stable").reset_index(drop=True) if not d.empty else d
        self.H = (np.sort(self.draws[NUM_COLS].to_numpy().astype(int), axis=1)
                  if not self.draws.empty else np.zeros((0, 6), dtype=int))

    # --- podstawowe zbiory
    @cached_property
    def last_draw(self) -> set[int]:
        return set(int(x) for x in self.H[-1]) if len(self.H) else set()

    @cached_property
    def hot(self) -> list[int]:
        """10 liczb z największą liczbą trafień w ostatnich 100 losowaniach (remis: mniejsza liczba)."""
        recent = self.H[-RECENT_WINDOW:]
        cnt = np.bincount(recent.ravel(), minlength=50)[1:50] if len(recent) else np.zeros(49, int)
        return sorted(range(1, 50), key=lambda n: (-cnt[n - 1], n))[:TOP]

    @cached_property
    def cold(self) -> list[int]:
        """10 liczb, które najdłużej nie padły (bez wystąpień = na początku)."""
        n_draws = len(self.H)
        since = {}
        for n in range(1, 50):
            hit = np.flatnonzero((self.H == n).any(1))
            since[n] = n_draws - 1 - hit[-1] if len(hit) else 10**9
        return sorted(range(1, 50), key=lambda n: (-since[n], n))[:TOP]

    @cached_property
    def pairs(self) -> np.ndarray:
        """P[a, b] = ile razy a i b padły razem (symetryczna 50×50)."""
        P = np.zeros((50, 50), dtype=np.int32)
        for i, j in itertools.combinations(range(6), 2):
            np.add.at(P, (self.H[:, i], self.H[:, j]), 1)
        return P + P.T

    @cached_property
    def pair_factor(self) -> np.ndarray:
        """Mnożnik wagi: częstość pary / średnia częstość pary (dla pustej historii = 1)."""
        exp = len(self.H) * 15 / math.comb(49, 2)
        return (self.pairs + 1) / (exp + 1)

    @cached_property
    def triples(self) -> np.ndarray:
        T = np.zeros((50, 50, 50), dtype=np.int32)
        for i, j, k in itertools.combinations(range(6), 3):
            np.add.at(T, (self.H[:, i], self.H[:, j], self.H[:, k]), 1)
        # symetria: T[a,b,c] dla dowolnej kolejności
        out = np.zeros_like(T)
        for perm in itertools.permutations(range(3)):
            out += T.transpose(perm)
        return out

    @cached_property
    def triple_factor(self) -> np.ndarray:
        exp = len(self.H) * 20 / math.comb(49, 3)
        return (self.triples + 1) / (exp + 1)

    def subsets(self, k: int) -> set[tuple[int, ...]]:
        """Wszystkie k-elementowe podzbiory losowań z historii (do filtra podobieństwa)."""
        cache = self.__dict__.setdefault("_subsets", {})
        if k not in cache:
            s: set[tuple[int, ...]] = set()
            for row in self.H.tolist():
                s.update(itertools.combinations(row, k))
            cache[k] = s
        return cache[k]

    # --- maski reguł
    def similar_ok(self, M: np.ndarray, k: int) -> np.ndarray:
        S = self.subsets(k)
        return np.array([not any(c in S for c in itertools.combinations(row, k)) for row in M.tolist()], dtype=bool)

    def mask(self, key: str, M: np.ndarray, similar_min: int = SIMILAR_DEFAULT) -> np.ndarray:
        if key == "suma":
            return _sum_ok(M)
        if key == "parzyste":
            return _even_ok(M)
        if key == "niskie":
            return _low_ok(M)
        if key == "dziesiatki":
            return _decades_ok(M)
        if key == "koncowki":
            return _endings_ok(M)
        if key == "kolejne":
            return _consecutive_ok(M)
        if key == "powtorki":
            last = np.zeros(50, dtype=bool)
            last[list(self.last_draw)] = True
            return last[M].sum(1) <= 1
        if key == "podobne":
            return self.similar_ok(M, similar_min)
        if key == "goraco_zimno":
            hot = np.zeros(50, dtype=bool)
            hot[self.hot] = True
            cold = np.zeros(50, dtype=bool)
            cold[self.cold] = True
            return (hot[M].sum(1) >= 2) & (cold[M].sum(1) >= 1)
        if key == "popularne":
            return _popular_ok(M)
        raise FilterError(f"„{key}” nie jest regułą")

    # --- statystyki filtrów
    @cached_property
    def sample(self) -> np.ndarray:
        """Stała próbka losowych kombinacji (równomiernie z 13,98 mln) do szacowania, ile zostaje."""
        rng = np.random.default_rng(SAMPLE_SEED)
        keys = rng.random((SAMPLE_SIZE, 49))
        return np.sort(np.argpartition(keys, 6, axis=1)[:, :6] + 1, axis=1)

    def sample_mask(self, key: str, similar_min: int = SIMILAR_DEFAULT) -> np.ndarray:
        cache = self.__dict__.setdefault("_sample_masks", {})
        ck = (key, similar_min if key == "podobne" else None)
        if ck not in cache:
            cache[ck] = self.mask(key, self.sample, similar_min)
        return cache[ck]

    def history_pass_pct(self, key: str, similar_min: int = SIMILAR_DEFAULT) -> float | None:
        """Jaki % prawdziwych losowań przeszedłby regułę (dla 9 i 10: względem losowań wcześniejszych)."""
        H = self.H
        if len(H) < 2:
            return None
        if key == "powtorki":
            prev = np.zeros((len(H), 50), dtype=bool)
            prev[np.repeat(np.arange(1, len(H)), 6), H[:-1].ravel()] = True
            ok = prev[np.arange(1, len(H))[:, None], H[1:]].sum(1) <= 1
            return round(100 * float(ok.mean()), 1)
        if key == "podobne":
            seen: set[tuple[int, ...]] = set()
            ok = 0
            for row in H.tolist():
                subs = list(itertools.combinations(row, similar_min))
                ok += not any(c in seen for c in subs)
                seen.update(subs)
            return round(100 * ok / len(H), 1)
        if key == "goraco_zimno":
            return None           # zależy od chwili losowania — liczymy tylko udział kombinacji
        return round(100 * float(self.mask(key, H).mean()), 1)

    def kept_pct(self, keys: list[str], similar_min: int = SIMILAR_DEFAULT) -> float:
        return self.kept_estimate(keys, similar_min)["kept_pct"]

    def kept_estimate(self, keys: list[str], similar_min: int = SIMILAR_DEFAULT) -> dict:
        """Ile kombinacji zostaje po regułach (szacunek z próbki 50 000 losowych kombinacji)."""
        rules = [k for k in keys if BY_KEY[k].kind == "reguła"]
        hits = SAMPLE_SIZE
        if rules:
            m = np.ones(SAMPLE_SIZE, dtype=bool)
            for k in rules:
                m &= self.sample_mask(k, similar_min)
            hits = int(m.sum())
        pct = 100 * hits / SAMPLE_SIZE
        return {"kept_pct": pct, "kept_combos": round(TOTAL_COMBOS * hits / SAMPLE_SIZE),
                "sample_hits": hits, "sample_size": SAMPLE_SIZE, "precise": hits >= 50}


# ------------------------------------------------------------------ wybór filtrów
def conflicts(keys: list[str]) -> list[tuple[str, str]]:
    out = []
    for a, b in itertools.combinations(keys, 2):
        if b in BY_KEY[a].excludes or a in BY_KEY[b].excludes:
            out.append((a, b))
    return out


@dataclass
class ActiveFilters:
    """Zestaw włączonych filtrów gotowy do użycia w generatorze."""
    ctx: FilterContext
    keys: list[str] = field(default_factory=list)
    similar_min: int = SIMILAR_DEFAULT

    def __post_init__(self):
        seen = []
        for k in self.keys:
            if k not in BY_KEY:
                raise FilterError(f"Nieznany filtr: {k}")
            if k not in seen:
                seen.append(k)
        self.keys = sorted(seen, key=lambda k: BY_KEY[k].no)
        if self.similar_min not in (4, 5):
            raise FilterError("Próg podobieństwa musi wynosić 4 lub 5")
        bad = conflicts(self.keys)
        if bad:
            a, b = bad[0]
            raise FilterError(f"Filtry „{BY_KEY[a].name}” i „{BY_KEY[b].name}” wykluczają się "
                              "(jeden premiuje układy z historii, drugi je omija).")
        self.rules = [k for k in self.keys if BY_KEY[k].kind == "reguła"]
        self.use_pairs = "pary" in self.keys
        self.use_triples = "trojki" in self.keys
        if self.use_pairs:
            self._pf = self.ctx.pair_factor
        if self.use_triples:
            self._tf = self.ctx.triple_factor

    def __bool__(self) -> bool:
        return bool(self.keys)

    @property
    def has_weights(self) -> bool:
        return self.use_pairs or self.use_triples

    def pick_factor(self, cand: np.ndarray, picked: list[int]) -> np.ndarray:
        """Mnożniki wag kandydatów przy wyborze kolejnej liczby (filtry 1 i 2)."""
        f = np.ones(len(cand))
        if not picked:
            return f
        if self.use_pairs:
            f *= self._pf[np.ix_(cand, picked)].prod(axis=1)
        if self.use_triples and len(picked) >= 2:
            for a, b in itertools.combinations(picked, 2):
                f *= self._tf[a, b, cand]
        return f

    def rejects(self, combo: tuple[int, ...]) -> str | None:
        """Klucz pierwszej reguły, której kombinacja nie spełnia (None = przechodzi)."""
        if not self.rules:
            return None
        M = np.array([combo])
        for k in self.rules:
            if not self.ctx.mask(k, M, self.similar_min)[0]:
                return k
        return None

    def kept_pct(self) -> float:
        return self.ctx.kept_pct(self.keys, self.similar_min)

    def estimate(self) -> dict:
        return self.ctx.kept_estimate(self.keys, self.similar_min)


def describe(ctx: FilterContext) -> list[dict]:
    """Opis wszystkich filtrów + statystyki (do API i do plików strony)."""
    out = []
    for f in FILTERS:
        item = {
            "key": f.key, "no": f.no, "name": f.name, "kind": f.kind, "short": f.short, "info": f.info,
            "excludes": list(f.excludes),
        }
        if f.kind == "reguła":
            if f.key == "podobne":
                item["variants"] = {
                    str(k): {"kept_pct": round(ctx.kept_pct([f.key], k), 3),
                             "history_pct": ctx.history_pass_pct(f.key, k)} for k in (4, 5)}
                item["kept_pct"] = item["variants"][str(SIMILAR_DEFAULT)]["kept_pct"]
                item["history_pct"] = item["variants"][str(SIMILAR_DEFAULT)]["history_pct"]
            else:
                item["kept_pct"] = round(ctx.kept_pct([f.key]), 1)
                item["history_pct"] = ctx.history_pass_pct(f.key)
        else:
            item["kept_pct"] = None
            item["history_pct"] = None
        out.append(item)
    # dodatkowe fakty do opisów wag
    P = ctx.pairs
    iu = np.triu_indices(50, 1)
    vals = P[iu]
    sel = (iu[0] >= 1)
    a, b, v = iu[0][sel], iu[1][sel], vals[sel]
    top = int(np.argmax(v))
    exp2 = len(ctx.H) * 15 / math.comb(49, 2)
    out[0]["facts"] = {"top_pair": [int(a[top]), int(b[top])], "top_count": int(v[top]),
                       "mean": round(exp2, 1), "std": round(float(v.std()), 1),
                       "random_std": round(math.sqrt(exp2 * (1 - 15 / math.comb(49, 2))), 1)}
    T = ctx.triples
    a3, b3, c3 = np.array(list(itertools.combinations(range(1, 50), 3))).T
    v3 = T[a3, b3, c3]
    i3 = int(np.argmax(v3))
    best_t, best = [int(a3[i3]), int(b3[i3]), int(c3[i3])], int(v3[i3])
    exp3 = len(ctx.H) * 20 / math.comb(49, 3)
    out[1]["facts"] = {"top_triple": best_t, "top_count": best, "mean": round(exp3, 1)}
    return out
