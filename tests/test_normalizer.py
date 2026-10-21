import datetime as dt

import openpyxl
import pytest

from conftest import FAKE, to_csv_text
from src.normalizer import NormalizationError, normalize_file, normalize_rows, parse_date


def test_prawidlowy_import_csv(tmp_path, fake_rows):
    p = tmp_path / "a.csv"; p.write_text(to_csv_text(fake_rows), encoding="utf-8")
    r = normalize_file(p)
    assert len(r.draws) == 5 and r.errors.empty
    assert list(r.draws.columns) == ["draw_id", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6"]
    assert r.report["dane kompletne i gotowe do analizy"] == "TAK"


@pytest.mark.parametrize("sep", [",", ";", "\t"])
def test_separatory(tmp_path, fake_rows, sep):
    p = tmp_path / "a.csv"; p.write_text(to_csv_text(fake_rows, sep), encoding="utf-8")
    assert len(normalize_file(p).draws) == 5


@pytest.mark.parametrize("enc", ["utf-8", "utf-8-sig", "cp1250"])
def test_kodowania(tmp_path, enc):
    rows = [["nr", "data", "n1", "n2", "n3", "n4", "n5", "n6", "uwagi"],
            [1, "02-01-2024", 1, 2, 3, 4, 5, 6, "zażółć gęślą jaźń"]]
    p = tmp_path / "a.csv"; p.write_bytes(to_csv_text(rows, ";").encode(enc))
    r = normalize_file(p)
    assert len(r.draws) == 1 and r.report["dodatkowe kolumny (pominięte)"] == 1


@pytest.mark.parametrize("txt,expected", [("2024-01-02", dt.date(2024, 1, 2)), ("02-01-2024", dt.date(2024, 1, 2)),
                                          ("02.01.2024", dt.date(2024, 1, 2)), ("02/01/2024", dt.date(2024, 1, 2))])
def test_konwersja_dat(txt, expected):
    assert parse_date(txt) == expected


@pytest.mark.parametrize("bad", ["32-01-2024", "2024-13-01", "wczoraj", "", "31-02-2024"])
def test_bledne_daty(bad):
    with pytest.raises(ValueError):
        parse_date(bad)


def _with(fake_rows, row):
    return fake_rows + [row]


def test_brakujace_wartosci(fake_rows):
    r = normalize_rows(_with(fake_rows, [6, "2024-01-13", 1, 2, 3, None, 5, 6]))
    assert len(r.draws) == 5 and len(r.errors) == 1 and "brak wartości" in r.errors.iloc[0]["powód"]


def test_liczby_spoza_zakresu(fake_rows):
    r = normalize_rows(_with(fake_rows, [6, "2024-01-13", 0, 2, 3, 4, 5, 50]))
    assert len(r.errors) == 1 and "poza zakresem" in r.errors.iloc[0]["powód"]


def test_powtorzona_liczba(fake_rows):
    r = normalize_rows(_with(fake_rows, [6, "2024-01-13", 1, 1, 3, 4, 5, 6]))
    assert "powtórzona" in r.errors.iloc[0]["powód"]


def test_duplikaty_losowan(fake_rows):
    r = normalize_rows(_with(_with(fake_rows, [1, "2024-02-01", 9, 8, 7, 6, 5, 4]), [9, "2024-01-02", 6, 5, 4, 3, 2, 1]))
    assert len(r.draws) == 5 and len(r.errors) == 2 and r.report["duplikatów"] == 2


def test_bledna_data_w_rekordzie_nie_usuwa_po_cichu(fake_rows):
    r = normalize_rows(_with(fake_rows, [6, "31-02-2024", 1, 2, 3, 4, 5, 6]))
    assert len(r.errors) == 1 and r.report["rekordów do ręcznej weryfikacji"] == 1
    assert r.report["dane kompletne i gotowe do analizy"].startswith("NIE")


def test_liczby_jako_tekst_i_odwrotna_kolejnosc(fake_rows):
    rows = [fake_rows[0]] + [[str(v) if i != 1 else v for i, v in enumerate(r)] for r in reversed(fake_rows[1:])]
    r = normalize_rows(rows)
    assert list(r.draws["draw_id"]) == [1, 2, 3, 4, 5]  # posortowane chronologicznie


def test_pusty_plik(tmp_path):
    p = tmp_path / "e.csv"; p.write_text("", encoding="utf-8")
    with pytest.raises(NormalizationError):
        normalize_file(p)


def test_brak_kolumny_daty():
    with pytest.raises(NormalizationError):
        normalize_rows([["a", "b"], [1, 2]])


def test_uklad_jak_w_excelu_uzytkownika(tmp_path):
    """nr | data | WYNIKI | (5 kolumn bez nagłówka), pierwsza liczba jako tekst '09', dodatkowe tabele z boku."""
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Arkusz1"; wb.create_sheet("Arkusz2")
    ws.append(["nr", "data", "WYNIKI"])
    ws.append([4477.0, "01-01-2008", "09", 19.0, 20.0, 31.0, 45.0, 48.0, 1.0, 140])
    ws.append([4478.0, "03-01-2008", "01", 7.0, 10.0, 21.0, 35.0, 46.0])
    ws.append([None] * 8)
    p = tmp_path / "x.xlsx"; wb.save(p)
    r = normalize_file(p)
    assert len(r.draws) == 2 and r.errors.empty
    assert r.draws.iloc[0][["n1", "n2", "n3", "n4", "n5", "n6"]].tolist() == [9, 19, 20, 31, 45, 48]
    assert r.draws.iloc[0]["draw_date"] == dt.date(2008, 1, 1)
