"""Filtry trybu ekspert (src/filters.py) i ich użycie w generatorze."""
import itertools

import numpy as np
import pytest

from src import filters as F
from src import generator as gen
from src.data_loader import load_canonical_csv

M = lambda *rows: np.array([sorted(r) for r in rows])  # noqa: E731


@pytest.fixture(scope="module")
def real():
    d = load_canonical_csv("data/lotto_normalized.csv")
    return d, F.FilterContext(d)


def test_rules_on_examples(fake_draws):
    ctx = F.FilterContext(fake_draws)
    ok = M([5, 17, 23, 30, 38, 44])
    assert not ctx.mask("suma", M([1, 2, 4, 6, 8, 10]))[0]           # suma 31
    assert ctx.mask("suma", ok)[0]
    assert not ctx.mask("parzyste", M([2, 4, 6, 8, 10, 13]))[0]          # 5 parzystych
    assert not ctx.mask("niskie", M([1, 2, 5, 7, 9, 30]))[0]             # 5 niskich
    assert not ctx.mask("dziesiatki", M([30, 31, 34, 36, 2, 45]))[0]     # 4 z trzydziestek
    assert not ctx.mask("koncowki", M([3, 13, 23, 30, 41, 45]))[0]       # 3× końcówka 3
    assert not ctx.mask("kolejne", M([4, 5, 20, 21, 33, 40]))[0]         # 2 pary kolejnych
    assert ctx.mask("kolejne", M([4, 5, 20, 22, 33, 40]))[0]
    assert not ctx.mask("popularne", M([1, 7, 12, 19, 25, 31]))[0]       # same daty (≤31)
    assert not ctx.mask("popularne", M([5, 10, 15, 20, 33, 47]))[0]      # ciąg co 5
    assert ctx.mask("popularne", M([5, 10, 15, 22, 33, 47]))[0]
    # ostatnie sztuczne losowanie: 7 8 9 13 14 15
    assert not ctx.mask("powtorki", M([7, 8, 20, 30, 40, 45]))[0]
    assert ctx.mask("powtorki", M([7, 18, 20, 30, 40, 45]))[0]
    # podobne: losowanie 2 to 1 2 3 10 20 30
    assert not ctx.mask("podobne", M([1, 2, 3, 10, 41, 47]), 4)[0]
    assert ctx.mask("podobne", M([1, 2, 3, 11, 41, 47]), 5)[0]


def test_vectorised_masks_match_scalar(real):
    _, ctx = real
    S = ctx.sample[:300]
    for f in F.FILTERS:
        if f.kind != "reguła":
            continue
        vec = ctx.mask(f.key, S)
        one = np.array([ctx.mask(f.key, row[None, :])[0] for row in S])
        assert (vec == one).all(), f.key


def test_conflicts_and_validation(real):
    _, ctx = real
    with pytest.raises(F.FilterError):
        F.ActiveFilters(ctx, ["pary", "podobne"])
    with pytest.raises(F.FilterError):
        F.ActiveFilters(ctx, ["trojki", "podobne"])
    with pytest.raises(F.FilterError):
        F.ActiveFilters(ctx, ["nieznany"])
    with pytest.raises(F.FilterError):
        F.ActiveFilters(ctx, ["podobne"], similar_min=3)
    allowed = [f.key for f in F.FILTERS if f.key != "podobne"]
    assert F.ActiveFilters(ctx, allowed).keys == allowed


def test_stats_are_honest(real):
    """Proste reguły: % zostających kombinacji ≈ % losowań z historii, które by przeszły."""
    _, ctx = real
    for k in ["suma", "parzyste", "niskie", "dziesiatki", "koncowki", "kolejne", "popularne"]:
        assert abs(ctx.kept_pct([k]) - ctx.history_pass_pct(k)) < 2.5, k
    assert ctx.kept_pct(["podobne"], 4) < 0.2           # od 4 wspólnych zostaje znikoma część
    assert ctx.kept_pct(["podobne"], 5) > 80


def test_hot_cold_match_site_stats(real):
    from api.service import LottoService
    d, ctx = real
    s = LottoService(d).stats
    assert ctx.hot == s["hot_recent"] and ctx.cold == s["longest_absent"]


def test_generator_respects_all_rules(real):
    d, ctx = real
    keys = [f.key for f in F.FILTERS if f.key not in ("pary", "trojki")]
    af = F.ActiveFilters(ctx, keys, similar_min=4)
    hist = gen.history_set(d)
    sub4 = ctx.subsets(4)
    for seed in range(3):
        r = gen.losuj6(d, filters=af, history=hist, rng=np.random.default_rng(seed))
        assert af.rejects(r.numbers) is None
        assert not any(c in sub4 for c in itertools.combinations(r.numbers, 4))
        assert not gen.has_triple(r.numbers)
        assert sum(r.rejected_filters.values()) == r.attempts - 1 - r.rejected_history


def test_pair_weights_shift_choice(real):
    d, ctx = real
    af = F.ActiveFilters(ctx, ["pary"])
    P = ctx.pairs
    a = int(np.argmax(P[31]))                        # najczęstszy partner liczby 31
    f = af.pick_factor(np.array([a, 2]), [31])
    assert f[0] > 1 and f[0] > f[1] * 0.9


def test_impossible_filters_fail_fast(fake_draws):
    ctx = F.FilterContext(fake_draws)
    af = F.ActiveFilters(ctx, ["suma"])
    af.rules = ["suma"]
    ctx.mask = lambda key, M, similar_min=4: np.zeros(len(M), dtype=bool)  # nic nie przechodzi
    with pytest.raises(gen.GeneratorError):
        gen.losuj6(fake_draws, filters=af, rng=np.random.default_rng(0), time_budget=0.2)


def test_no_filters_unchanged(fake_draws):
    """Bez filtrów generator daje dokładnie to samo co wcześniej (ten sam ziarno = ten sam wynik)."""
    a = gen.losuj6(fake_draws, rng=np.random.default_rng(7))
    b = gen.losuj6(fake_draws, rng=np.random.default_rng(7), filters=None)
    assert a.numbers == b.numbers and b.rejected_filters == {}
