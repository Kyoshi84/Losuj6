"""Test dymny interfejsu: każdy widok renderuje się bez wyjątku na (sztucznej) bazie."""
import pytest

from src.normalizer import write_canonical_csv

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

VIEWS = ["Dashboard", "Statystyki liczb", "Porównanie okresów", "Historia losowań",
         "Import i jakość danych", "Konfiguracja i aktualizacja"]


@pytest.mark.parametrize("view", VIEWS)
def test_widok_renderuje_sie(view, tmp_path, fake_draws, monkeypatch):
    db = tmp_path / "db.csv"; write_canonical_csv(fake_draws, db)
    monkeypatch.setenv("LOTTO_DATA_PATH", str(db))
    at = AppTest.from_file(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    at.sidebar.radio[0].set_value(view).run()
    assert not at.exception, [e.value for e in at.exception]


def test_pusta_baza_nie_wywala_aplikacji(tmp_path, monkeypatch):
    monkeypatch.setenv("LOTTO_DATA_PATH", str(tmp_path / "brak.csv"))
    at = AppTest.from_file(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    assert not at.exception and any("pusta" in e.value for e in at.error)
