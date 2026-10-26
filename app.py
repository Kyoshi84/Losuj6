"""Lotto — analiza statystyk. Uruchomienie: streamlit run app.py"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import combinations as cb
from src import statistics_engine as se
from src.api_client import ApiConfig, ApiError, LottoApiClient
from src.data_loader import load_canonical_csv
from src.data_sources import ApiDataSource, FrameSource
from src.exporter import build_xlsx_report, df_to_csv_bytes
from src.normalizer import NormalizationError, NormalizationResult, normalize_file, normalize_rows, report_to_markdown
from src.sync import replace_database, sync_into_csv

ROOT = Path(__file__).parent


def _load_dotenv(path: Path) -> None:
    """Minimalny odczyt pliku .env (KLUCZ=wartość). Nie nadpisuje zmiennych już ustawionych w systemie."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")
DATA_PATH = Path(os.getenv("LOTTO_DATA_PATH", ROOT / "data" / "lotto_normalized.csv"))
LOG_PATH = DATA_PATH.parent / "sync_log.json"
STALE_DAYS = 7

st.set_page_config(page_title="Lotto — statystyki", page_icon="🎱", layout="wide")


@st.cache_data(show_spinner=False)
def load_db(path: str, mtime: float) -> pd.DataFrame:
    return load_canonical_csv(path)


def get_db() -> pd.DataFrame:
    mtime = DATA_PATH.stat().st_mtime if DATA_PATH.exists() else 0.0
    return load_db(str(DATA_PATH), mtime)


def show_messages(info: se.PeriodInfo) -> None:
    for m in info.messages:
        st.warning(m)


def disclaimer() -> None:
    st.info(se.DISCLAIMER)


def empty_notice() -> None:
    st.error(f"Baza jest pusta lub nie istnieje ({DATA_PATH}). Wgraj dane w widoku „Import i jakość danych”.")


# --------------------------------------------------------------------- wybór okresu
def period_picker(db: pd.DataFrame, key: str, default: str = "Cała historia"):
    """Zwraca (dane okresu, etykieta, Period | None, PeriodInfo). Ten sam zakres trafia do tabel i eksportu."""
    modes = ["Cała historia", "Ostatni miesiąc (od dziś)", "Ostatni miesiąc danych w bazie", "Własny zakres dat"]
    mode = st.radio("Okres analizy", modes, index=modes.index(default), horizontal=True, key=f"mode_{key}")
    dmin, dmax = db["draw_date"].min().date(), db["draw_date"].max().date()
    period = None
    if mode == "Ostatni miesiąc (od dziś)":
        period = se.last_month_period(dt.date.today())
    elif mode == "Ostatni miesiąc danych w bazie":
        period = se.Period(se.one_month_back(dmax), dmax)
    elif mode == "Własny zakres dat":
        rng = st.date_input("Zakres dat", (max(dmin, dmax - dt.timedelta(days=90)), dmax),
                            min_value=dmin, max_value=dt.date.today(), key=f"range_{key}")
        period = se.Period(*rng) if isinstance(rng, tuple) and len(rng) == 2 else se.Period(dmin, dmax)
    sub = se.filter_period(db, period)
    info = se.describe_period(db, period)
    label = period.label() if period else f"{dmin} – {dmax} (cała historia)"
    st.caption(f"Analizowany okres: **{label}** · losowań: **{len(sub)}**")
    show_messages(info)
    return sub, label, period, info


# --------------------------------------------------------------------- widoki
def view_dashboard(db: pd.DataFrame) -> None:
    st.title("🎱 Dashboard")
    if db.empty:
        return empty_notice()
    last = db["draw_date"].max().date()
    age = (dt.date.today() - last).days
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Przeanalizowane losowania", f"{len(db):,}".replace(",", " "))
    c2.metric("Początek danych", str(db["draw_date"].min().date()))
    c3.metric("Ostatnie losowanie w bazie", str(last))
    c4.metric("Wiek danych", f"{age} dni")
    if age > STALE_DAYS:
        st.warning(f"Dane są nieaktualne: ostatnie losowanie w bazie było {age} dni temu. "
                   "Uzupełnij bazę w widoku „Import i jakość danych”.")
    else:
        st.success("Dane są aktualne.")
    stats = se.number_stats(db)
    left, right = st.columns(2)
    cols = ["liczba", "wystąpienia", "% losowań", "ranking", "remis na granicy"]
    top, bottom = se.top_n(stats, 10, True), se.top_n(stats, 10, False)
    left.subheader("TOP 10 najczęstszych")
    left.dataframe(top[cols], hide_index=True, width="stretch")
    right.subheader("TOP 10 najrzadszych")
    right.dataframe(bottom[cols], hide_index=True, width="stretch")
    if (top["remis na granicy"] == "tak").any() or (bottom["remis na granicy"] == "tak").any():
        st.caption("Remis na granicy TOP 10: pokazano wszystkie liczby z takim samym wynikiem, więc wierszy może być więcej niż 10.")
    t = se.uniformity_test(stats)
    if t["p"] is not None:
        st.caption(f"Test χ² zgodności z rozkładem równomiernym: χ² = {t['chi2']:.1f}, p = {t['p']:.2f}. "
                   + ("Rozrzut mieści się w normie losowej." if t["p"] >= 0.05 else "Odchylenie wymaga uwagi (sprawdź dane)."))
    disclaimer()


def view_stats(db: pd.DataFrame) -> None:
    st.title("📊 Statystyki liczb")
    if db.empty:
        return empty_notice()
    sub, label, _, _ = period_picker(db, "stats")
    stats = se.number_stats(sub)
    if not se.validate_sum(sub, stats):
        st.error("Błąd walidacji: suma wystąpień ≠ 6 × liczba losowań.")
    else:
        st.caption(f"✔ Walidacja: suma wystąpień = {int(stats['wystąpienia'].sum())} = 6 × {len(sub)}.")
    tab1, tab2, tab3, tab4 = st.tabs(["Pełna tabela", "TOP 10", "Niewystępujące", "Najdawniej"])
    with tab1:
        st.dataframe(stats, hide_index=True, width="stretch", height=620)
        st.caption("Kliknij nagłówek kolumny, aby sortować. „remis” oznacza, że kilka liczb ma ten sam wynik i tę samą pozycję.")
    with tab2:
        a, b = se.top_n(stats, 10, True), se.top_n(stats, 10, False)
        c1, c2 = st.columns(2)
        c1.subheader("Najczęstsze"); c1.dataframe(a[["liczba", "wystąpienia", "% losowań", "ranking", "remis na granicy"]], hide_index=True)
        c2.subheader("Najrzadsze"); c2.dataframe(b[["liczba", "wystąpienia", "% losowań", "ranking", "remis na granicy"]], hide_index=True)
        top_export = pd.concat([a.assign(zestawienie="najczęstsze"), b.assign(zestawienie="najrzadsze")])
    with tab3:
        nd = se.never_drawn(stats)
        st.write("Wszystkie liczby wystąpiły w tym okresie." if nd.empty else f"Liczby bez wystąpień: {', '.join(map(str, nd['liczba']))}")
    with tab4:
        st.dataframe(se.longest_absent(stats, 10)[["liczba", "ostatnie wystąpienie", "losowań od ostatniego"]], hide_index=True)
    st.subheader("Eksport (dla widocznego okresu)")
    safe = label.replace(" ", "").replace("–", "_").split("(")[0]
    e1, e2, e3 = st.columns(3)
    e1.download_button("Pełna tabela CSV", df_to_csv_bytes(stats), f"statystyki_{safe}.csv", "text/csv")
    e2.download_button("TOP 10 CSV", df_to_csv_bytes(top_export), f"top10_{safe}.csv", "text/csv")
    xres = NormalizationResult(sub, pd.DataFrame(columns=["wiersz", "powód"]), {"okres": label, "losowań": len(sub)})
    e3.download_button("Raport XLSX", build_xlsx_report(xres, stats, "okres"), f"raport_{safe}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    disclaimer()


def view_compare(db: pd.DataFrame) -> None:
    st.title("⚖️ Porównanie okresów")
    if db.empty:
        return empty_notice()
    sub, label, _, info = period_picker(db, "cmp", default="Ostatni miesiąc danych w bazie")
    if sub.empty:
        st.info("W wybranym okresie nie ma losowań, więc nie ma z czym porównywać. Zmień okres.")
        return
    stats_all, stats_p = se.number_stats(db), se.number_stats(sub)
    cmp = se.compare_periods(stats_all, stats_p)
    metric = st.radio("Wartość na wykresie", ["% losowań", "liczba wystąpień"], horizontal=True)
    a, b = ("% losowań (całość)", "% losowań (okres)") if metric == "% losowań" else ("wystąpienia (całość)", "wystąpienia (okres)")
    if metric == "liczba wystąpień":
        st.caption("Uwaga: okresy mają różną liczbę losowań, więc surowe liczby nie są wprost porównywalne. Lepszy jest wykres w %.")
    fig = go.Figure([go.Bar(x=cmp["liczba"], y=cmp[a], name="Cała historia"),
                     go.Bar(x=cmp["liczba"], y=cmp[b], name=f"Okres {label}")])
    fig.update_layout(barmode="group", xaxis=dict(title="liczba", dtick=1), yaxis_title=metric, height=450,
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.subheader("Największe różnice")
    big = cmp.reindex(cmp["różnica % (pkt proc.)"].abs().sort_values(ascending=False).index).head(8)
    st.dataframe(big, hide_index=True, width="stretch")
    up, down = se.biggest_movers(cmp, 5)
    c1, c2 = st.columns(2)
    c1.subheader("Największe awanse w rankingu"); c1.dataframe(up[["liczba", "ranking (całość)", "ranking (okres)", "zmiana pozycji"]], hide_index=True)
    c2.subheader("Największe spadki w rankingu"); c2.dataframe(down[["liczba", "ranking (całość)", "ranking (okres)", "zmiana pozycji"]], hide_index=True)
    st.download_button("Pobierz porównanie CSV", df_to_csv_bytes(cmp), "porownanie_okresow.csv", "text/csv")
    disclaimer()


def view_history(db: pd.DataFrame) -> None:
    st.title("🗂️ Historia losowań")
    if db.empty:
        return empty_notice()
    dmin, dmax = db["draw_date"].min().date(), db["draw_date"].max().date()
    c1, c2 = st.columns(2)
    exact = c1.text_input("Szukaj po dacie (RRRR-MM-DD lub DD-MM-RRRR)")
    rng = c2.date_input("Zakres dat", (dmin, dmax), min_value=dmin, max_value=dmax)
    sub = db
    if isinstance(rng, tuple) and len(rng) == 2:
        sub = se.filter_period(db, se.Period(*rng))
    if exact.strip():
        from src.normalizer import parse_date
        try:
            day = pd.Timestamp(parse_date(exact))
            sub = sub[sub["draw_date"] == day]
            if sub.empty:
                st.info(f"Brak losowania z datą {day.date()} w wybranym zakresie.")
        except ValueError as e:
            st.error(str(e))
    show = sub.sort_values("draw_date", ascending=False).copy()
    show["draw_date"] = show["draw_date"].dt.date
    st.dataframe(show, hide_index=True, width="stretch", height=520)
    st.caption(f"Wyświetlono {len(show)} z {len(db)} losowań.")
    if st.button("Sprawdź poprawność widocznych rekordów"):
        rows = [["draw_id", "draw_date", *se.NUM_COLS]] + show.assign(draw_date=show["draw_date"].astype(str)).values.tolist()
        res = normalize_rows(rows)
        if res.errors.empty:
            st.success(f"Wszystkie {len(res.draws)} rekordów są poprawne (zakres 1–49, 6 różnych liczb, brak duplikatów).")
        else:
            st.error(f"Znaleziono {len(res.errors)} problemów.")
            st.dataframe(res.errors, hide_index=True)
    st.download_button("Pobierz widoczne losowania CSV", df_to_csv_bytes(show), "historia_losowan.csv", "text/csv")


def view_import(db: pd.DataFrame) -> None:
    st.title("📥 Import i jakość danych")
    st.write(f"Używana baza: `{DATA_PATH}` — {len(db)} losowań.")
    up = st.file_uploader("Wgraj nowy plik (CSV lub XLSX)", type=["csv", "txt", "xlsx"])
    if up is None:
        st.caption("Plik zostanie zwalidowany przed jakąkolwiek zmianą bazy. Oryginał nie jest nigdy nadpisywany.")
        return
    try:
        res = normalize_file(up.getvalue(), up.name)
    except NormalizationError as e:
        st.error(f"Nie można odczytać pliku: {e}")
        return
    except Exception as e:  # noqa: BLE001
        st.error(f"Nieoczekiwany błąd podczas odczytu pliku: {e}")
        return
    st.subheader("Raport normalizacji")
    st.table(pd.DataFrame({"parametr": res.report.keys(), "wartość": [str(v) for v in res.report.values()]}))
    if not res.errors.empty:
        st.error(f"{len(res.errors)} rekordów wymaga ręcznej weryfikacji (nie zostały usunięte po cichu — są poniżej).")
        st.dataframe(res.errors.astype(str), hide_index=True)
    if not res.draws.empty:
        prev = res.draws.copy(); prev["draw_date"] = prev["draw_date"].astype(str)
        st.dataframe(prev.head(20), hide_index=True)
    d1, d2, d3 = st.columns(3)
    norm_csv = res.draws.assign(draw_date=res.draws["draw_date"].astype(str)) if not res.draws.empty else res.draws
    d1.download_button("Znormalizowany CSV", df_to_csv_bytes(norm_csv), "lotto_normalized.csv", "text/csv")
    d2.download_button("Raport XLSX", build_xlsx_report(res), "raport_normalizacji.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d3.download_button("Raport MD", report_to_markdown(res).encode("utf-8"), "raport_normalizacji.md", "text/markdown")
    if res.draws.empty:
        return
    st.subheader("Aktualizacja bazy")
    mode = st.radio("Sposób", ["Dołącz tylko nowe losowania (bez duplikatów)", "Zastąp całą bazę tym plikiem"])
    allow = True
    if not res.errors.empty:
        allow = st.checkbox("Zastosuj tylko poprawne rekordy; błędne zostają do ręcznej weryfikacji")
    if st.button("Zastosuj", disabled=not allow, type="primary"):
        if mode.startswith("Dołącz"):
            r = sync_into_csv(FrameSource(res, up.name), DATA_PATH, LOG_PATH, allow_partial=True)
            (st.success if r.ok else st.error)(r.message)
        else:
            backup = replace_database(res.draws, DATA_PATH)
            st.success("Baza zastąpiona." + (f" Kopia poprzedniej: `{backup.name}`." if backup else ""))
        st.cache_data.clear()


def view_config(db: pd.DataFrame) -> None:
    st.title("⚙️ Konfiguracja i aktualizacja")
    st.write(f"**Lokalizacja pliku danych:** `{DATA_PATH}`")
    if DATA_PATH.exists():
        st.write("**Ostatnia modyfikacja pliku:** " + dt.datetime.fromtimestamp(DATA_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.error("Plik danych nie istnieje.")
    client = LottoApiClient(ApiConfig.from_env())
    st.write(f"**Status integracji API:** {client.status()}")
    st.caption("Adres API, autoryzacja i format odpowiedzi nie są potwierdzone — patrz README, sekcja „API”.")
    if st.button("Odśwież z API", disabled=not client.config.configured):
        last_id = int(db["draw_id"].max()) if not db.empty and db["draw_id"].notna().any() else None
        r = sync_into_csv(ApiDataSource(client, after_draw_id=last_id), DATA_PATH, LOG_PATH)
        (st.success if r.ok else st.error)(r.message)
        st.cache_data.clear()
    if not client.config.configured:
        st.caption("Przycisk jest nieaktywny: ustaw LOTTO_API_BASE_URL i LOTTO_API_KEY (plik .env / zmienne środowiskowe).")
    st.subheader("Historia synchronizacji")
    if LOG_PATH.exists():
        try:
            st.dataframe(pd.DataFrame(json.loads(LOG_PATH.read_text(encoding="utf-8"))).iloc[::-1], hide_index=True)
        except ValueError:
            st.warning("Plik dziennika synchronizacji jest uszkodzony.")
    else:
        st.caption("Brak wpisów — nie wykonano jeszcze żadnej synchronizacji.")


@st.cache_data(show_spinner=False)
def cached_combo_stats(draws: pd.DataFrame, k: int) -> pd.DataFrame:
    return cb.combo_stats(draws, k)


@st.cache_data(show_spinner=False)
def cached_benchmark(n_draws: int, k: int, observed: int) -> dict:
    return cb.null_benchmark(n_draws, k, sims=300, observed=observed)


def view_combos(db: pd.DataFrame) -> None:
    st.title("🔗 Pary i trójki")
    if db.empty:
        return empty_notice()
    sub, label, _, _ = period_picker(db, "combo")
    if sub.empty:
        st.info("W wybranym okresie nie ma losowań. Zmień okres.")
        return
    kind = st.radio("Rodzaj kombinacji", ["Pary", "Trójki"], horizontal=True)
    k = 2 if kind == "Pary" else 3
    word = cb.KIND[k]
    stats = cached_combo_stats(sub, k)
    n = len(sub)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Losowań w okresie", n)
    c2.metric(f"Możliwych {'par' if k == 2 else 'trójek'}", f"{cb.total_combinations(k):,}".replace(",", " "))
    c3.metric("Padło choć raz", f"{len(stats):,}".replace(",", " "))
    c4.metric("Oczekiwane wystąpienia", f"{n * cb.expected_per_draw(k):.2f}",
              help="Średnio tyle razy padałaby każda kombinacja przy równomiernym losowaniu.")
    if n < se.LOW_SAMPLE_DRAWS:
        st.warning(f"Ograniczona próba: tylko {n} losowań. Przy tak małej próbie większość kombinacji padła 0 lub 1 raz, "
                   "więc ranking składa się głównie z remisów.")

    top_n = st.slider("Ile pozycji w TOP", 5, 30, 10)
    top = cb.top_combos(stats, top_n)
    st.subheader(f"TOP {top_n} najczęstszych {'par' if k == 2 else 'trójek'}")
    show = top.table.drop(columns=["liczby"])
    st.dataframe(show, hide_index=True, width="stretch")
    if top.ties_at_boundary:
        extra = " Pokazano pierwsze 50 z nich." if top.truncated else ""
        st.caption(f"Remis na granicy TOP {top_n}: {top.ties_at_boundary} kombinacji ma ten sam wynik ({top.boundary_count}), "
                   f"więc nie rozstrzygam go arbitralnie i pokazuję je wszystkie.{extra}")
    if not top.table.empty:
        fig = go.Figure(go.Bar(x=top.table["kombinacja"], y=top.table["wystąpienia"], name="Faktycznie"))
        fig.add_hline(y=float(top.table["oczekiwane"].iloc[0]), line_dash="dash",
                      annotation_text="oczekiwane (losowo)", annotation_position="top left")
        fig.update_layout(height=380, xaxis_title=word, yaxis_title="wystąpienia", xaxis_tickangle=-45)
        st.plotly_chart(fig, width="stretch")

        leader = int(top.table["wystąpienia"].iloc[0])
        b = cached_benchmark(n, k, leader)
        st.subheader("Czy lider jest zaskakujący?")
        verdict = ("mieści się w normie losowej" if b["p"] >= 0.05 else
                   "jest wyższy niż zwykle w losowych danych, ale to nadal nie dowodzi, że losowanie jest zaburzone")
        st.write(f"Lider ({top.table['kombinacja'].iloc[0]}) padł **{leader}** razy. W {b['symulacji']} symulacjach czysto losowych "
                 f"danych o tej samej liczbie losowań najczęstsza kombinacja padała zwykle **{b['p05']:.0f}–{b['p95']:.0f}** razy "
                 f"(średnio {b['średnia']:.1f}). Co najmniej tyle wystąpień ({leader}) miał lider w **{100 * b['p']:.1f}%** symulacji, "
                 f"czyli wynik {verdict}.")
        st.caption("Ranking zawsze ma lidera — przy tysiącach kombinacji któraś musi paść najczęściej. Dlatego porównujemy go z liderem losowych danych, "
                   "a nie ze średnią. Przy sprawdzaniu wielu statystyk naraz pojedyncze p ≈ 0,02 zdarza się przypadkiem.")

    st.subheader("Sprawdź konkretną kombinację")
    chosen = st.multiselect(f"Wybierz {k} liczby (1–49)", list(range(1, 50)), max_selections=k, key=f"pick_{k}")
    if len(chosen) == k:
        combo = tuple(sorted(chosen))
        row = cb.lookup(stats, combo)
        name = cb.label(combo)
        if row is None:
            st.info(f"{word.capitalize()} {name} nie padła ani razu w tym okresie "
                    f"(oczekiwane przy losowaniu: {n * cb.expected_per_draw(k):.2f}).")
        else:
            st.success(f"{word.capitalize()} {name}: **{int(row['wystąpienia'])}** razy "
                       f"(oczekiwane {row['oczekiwane']}), pozycja {int(row['ranking'])}, "
                       f"ostatnio {row['ostatnie wystąpienie']} ({int(row['losowań od ostatniego'])} losowań temu).")
        yr = cb.yearly_counts(sub, combo)
        if len(yr) > 1:
            fig2 = go.Figure([go.Bar(x=yr["rok"], y=yr["wystąpienia"], name="Faktycznie"),
                              go.Scatter(x=yr["rok"], y=yr["oczekiwane"], name="Oczekiwane", mode="lines+markers")])
            fig2.update_layout(height=320, xaxis=dict(dtick=1, title="rok"), yaxis_title="wystąpienia", legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig2, width="stretch")
            st.caption("Ostatni rok może być niepełny (mniej losowań), dlatego obok pokazano oczekiwaną wartość dla tej liczby losowań.")
        hist = cb.combo_history(sub, combo)
        if not hist.empty:
            hist = hist.assign(draw_date=hist["draw_date"].dt.date).sort_values("draw_date", ascending=False)
            with st.expander(f"Losowania z tą kombinacją ({len(hist)})"):
                st.dataframe(hist, hide_index=True, width="stretch")
    elif chosen:
        st.caption(f"Wybierz dokładnie {k} liczby.")

    st.subheader("Eksport (dla widocznego okresu)")
    safe = label.replace(" ", "").replace("–", "_").split("(")[0]
    kn = "pary" if k == 2 else "trojki"
    e1, e2 = st.columns(2)
    e1.download_button(f"Wszystkie {kn}, które padły (CSV)", df_to_csv_bytes(stats.drop(columns=["liczby"])),
                       f"{kn}_{safe}.csv", "text/csv")
    e2.download_button(f"TOP {top_n} (CSV)", df_to_csv_bytes(show), f"{kn}_top{top_n}_{safe}.csv", "text/csv")
    st.info(cb.DISCLAIMER)


VIEWS = {
    "Dashboard": view_dashboard,
    "Statystyki liczb": view_stats,
    "Porównanie okresów": view_compare,
    "Pary i trójki": view_combos,
    "Historia losowań": view_history,
    "Import i jakość danych": view_import,
    "Konfiguracja i aktualizacja": view_config,
}

with st.sidebar:
    st.header("🎱 Lotto — statystyki")
    page = st.radio("Widok", list(VIEWS), label_visibility="collapsed")
    st.caption("Dane z lokalnego pliku CSV. Aplikacja nie przewiduje wyników losowań.")

try:
    database = get_db()
except Exception as e:  # noqa: BLE001
    st.error(f"Nie można wczytać bazy danych: {e}")
    database = pd.DataFrame(columns=["draw_id", "draw_date", *se.NUM_COLS])
    database["draw_date"] = pd.to_datetime(database["draw_date"])

VIEWS[page](database)
