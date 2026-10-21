import json

import pandas as pd
import pytest
import requests

from conftest import FAKE
from src.api_client import ApiConfig, ApiError, ApiNotConfiguredError, ApiNotImplementedError, LottoApiClient, map_api_record
from src.data_loader import load_canonical_csv
from src.data_sources import ApiDataSource, CsvDataSource, FrameSource, LotteryDataSource
from src.exporter import build_xlsx_report, df_to_csv_bytes
from src.normalizer import normalize_rows, write_canonical_csv
from src.sync import merge_draws, sync_into_csv

HEADER = ["draw_id", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6"]


def result_for(extra):
    return normalize_rows([HEADER] + [[i, d, *n] for i, d, n in extra])


class FakeClient:
    def __init__(self, records=None, fail=None):
        self.records, self.fail, self.calls = records or [], fail, []

    def fetch_raw(self, after_draw_id=None):
        self.calls.append(after_draw_id)
        if self.fail:
            raise self.fail
        return [r for r in self.records if after_draw_id is None or r["id"] > after_draw_id]


def mapper(r):
    return {"draw_id": r["id"], "draw_date": r["date"], **dict(zip(["n1", "n2", "n3", "n4", "n5", "n6"], r["nums"]))}


NEW = [{"id": 6, "date": "2024-01-13", "nums": [1, 2, 3, 4, 5, 6]}, {"id": 7, "date": "2024-01-16", "nums": [10, 11, 12, 13, 14, 15]}]


@pytest.fixture
def db(tmp_path, fake_draws):
    p = tmp_path / "data" / "db.csv"; p.parent.mkdir()
    write_canonical_csv(fake_draws, p)
    return p


def test_zrodla_maja_wspolny_interfejs(db):
    assert isinstance(CsvDataSource(db), LotteryDataSource) and isinstance(ApiDataSource(FakeClient(), mapper), LotteryDataSource)
    assert len(CsvDataSource(db).load().draws) == 5


def test_synchronizacja_dodaje_nowe_i_jest_idempotentna(db):
    src = ApiDataSource(FakeClient(NEW), mapper)
    r1 = sync_into_csv(src, db, db.parent / "log.json")
    assert r1.ok and r1.added == 2 and len(load_canonical_csv(db)) == 7
    r2 = sync_into_csv(src, db, db.parent / "log.json")       # ponowne pobranie tych samych losowań
    assert r2.ok and r2.added == 0 and r2.skipped == 2 and len(load_canonical_csv(db)) == 7
    log = json.loads((db.parent / "log.json").read_text(encoding="utf-8"))
    assert len(log) == 2 and log[0]["added"] == 2


def test_nieudana_synchronizacja_nie_niszczy_bazy(db):
    before = db.read_bytes()
    r = sync_into_csv(ApiDataSource(FakeClient(fail=ApiError("HTTP 503")), mapper), db, db.parent / "log.json")
    assert not r.ok and "503" in r.message and db.read_bytes() == before


def test_nieprawidlowe_nowe_dane_odrzucone_baza_nietknieta(db):
    before = db.read_bytes()
    bad = [{"id": 8, "date": "2024-01-18", "nums": [1, 1, 3, 4, 5, 6]}]
    r = sync_into_csv(ApiDataSource(FakeClient(bad), mapper), db)
    assert not r.ok and r.rejected == 1 and db.read_bytes() == before


def test_merge_bez_draw_id_uzywa_daty_i_liczb():
    a = normalize_rows([["data", "n1", "n2", "n3", "n4", "n5", "n6"], ["2024-01-02", 1, 2, 3, 4, 5, 6]]).draws
    merged, added, skipped = merge_draws(a, a)
    assert (len(merged), added, skipped) == (1, 0, 1)


def test_kopia_zapasowa_przy_zmianie(db):
    sync_into_csv(ApiDataSource(FakeClient(NEW), mapper), db)
    assert list(db.parent.glob("db.bak-*.csv"))


def test_domyslne_api_czeka_na_specyfikacje_i_nie_blokuje():
    client = LottoApiClient(ApiConfig(None, None))
    assert "nieskonfigurowane" in client.status()
    with pytest.raises(ApiNotConfiguredError):
        client._request("x")
    with pytest.raises(ApiNotImplementedError):
        map_api_record({})
    with pytest.raises(ApiNotImplementedError):
        ApiDataSource(LottoApiClient(ApiConfig("https://example.invalid", "k"))).load()


def test_klucz_api_nie_trafia_do_repr():
    assert "SEKRET" not in repr(ApiConfig("https://x", "SEKRET"))


def _client(monkeypatch, responses):
    cfg = ApiConfig("https://api.test", "k", timeout=1, max_retries=3, backoff=0)
    c = LottoApiClient(cfg, sleep=lambda s: None)
    monkeypatch.setattr(LottoApiClient, "_auth_headers", lambda self: {})
    calls = {"n": 0}

    class Resp:
        def __init__(self, code, body=None, headers=None): self.status_code, self._b, self.headers = code, body, headers or {}
        def json(self): return self._b

    def fake_get(url, **kw):
        r = responses[min(calls["n"], len(responses) - 1)]; calls["n"] += 1
        if isinstance(r, Exception): raise r
        return Resp(*r)

    monkeypatch.setattr(requests, "get", fake_get)
    return c, calls


def test_transport_ponawia_przy_5xx_i_timeoucie(monkeypatch):
    c, calls = _client(monkeypatch, [(503,), requests.Timeout(), (200, {"ok": 1})])
    assert c._request("d") == {"ok": 1} and calls["n"] == 3


def test_transport_limit_zapytan_429(monkeypatch):
    c, calls = _client(monkeypatch, [(429, None, {"Retry-After": "0"}), (200, [1])])
    assert c._request("d") == [1]


def test_transport_4xx_bez_ponawiania_i_wyczerpanie_prob(monkeypatch):
    c, calls = _client(monkeypatch, [(404,)])
    with pytest.raises(ApiError): c._request("d")
    assert calls["n"] == 1
    c, calls = _client(monkeypatch, [(500,)])
    with pytest.raises(ApiError, match="3 próbach"): c._request("d")
    assert calls["n"] == 3


def test_eksport_csv_i_xlsx(fake_draws):
    import io, openpyxl
    from src.statistics_engine import number_stats
    res = normalize_rows([HEADER] + [[i, d, *n] for i, d, n in FAKE] + [[9, "zła", 1, 2, 3, 4, 5, 6]])
    wb = openpyxl.load_workbook(io.BytesIO(build_xlsx_report(res, number_stats(fake_draws), "okres")))
    assert {"Losowania", "Błędy", "Raport"} <= set(wb.sheetnames) and wb["Losowania"].max_row == 6 and wb["Błędy"].max_row == 2
    assert df_to_csv_bytes(fake_draws).startswith(b"\xef\xbb\xbf")
