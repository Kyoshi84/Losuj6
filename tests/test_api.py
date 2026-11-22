"""API (FastAPI) i statyczne dane strony. Działa na prawdziwej bazie data/lotto_normalized.csv."""
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app, service  # noqa: E402
from api.service import LottoService, _ranges  # noqa: E402
from src.generator import has_triple  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_health_and_meta():
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["draws"] == len(service.draws)
    m = client.get("/api/meta").json()
    assert m["first_date"] <= m["last_date"]


def test_draws_filters_and_csv():
    r = client.get("/api/draws", params={"year": 1957}).json()
    assert r["total"] == r["count"] > 0
    assert all(d["draw_date"].startswith("1957") for d in r["draws"])
    r = client.get("/api/draws", params={"order": "desc", "limit": 3}).json()
    assert r["count"] == 3 and r["draws"][0] == client.get("/api/draws/latest").json()
    csv = client.get("/api/draws", params={"limit": 2, "format": "csv"})
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.splitlines()[0] == "draw_id,draw_date,n1,n2,n3,n4,n5,n6"
    assert len(csv.text.strip().splitlines()) == 3


def test_draw_by_id_and_404():
    assert client.get("/api/draws/1").json()["draw_date"] == "1957-01-27"
    assert client.get("/api/draws/999999").status_code == 404


def test_stats_consistent():
    s = client.get("/api/stats").json()
    assert len(s["numbers"]) == 49
    assert sum(x["count"] for x in s["numbers"]) == 6 * s["meta"]["draws"]
    counts = {x["number"]: x["count"] for x in s["numbers"]}
    assert counts[s["most_frequent"][0]] == max(counts.values())
    assert counts[s["least_frequent"][0]] == min(counts.values())
    assert {x["tier"] for x in s["numbers"]} == {"legenda", "epicka", "rzadka", "zwykła", "underdog"}
    assert client.get("/api/stats/50").status_code == 422
    period = client.get("/api/stats", params={"from": "2020-01-01", "to": "2020-12-31"}).json()
    assert sum(x["count"] for x in period["numbers"]) == 6 * period["meta"]["draws"]


def test_losuj_follows_generator_rules():
    for res in client.post("/api/losuj", json={"strength": 2, "count": 10}).json()["results"]:
        n = res["numbers"]
        assert len(set(n)) == 6 and all(1 <= x <= 49 for x in n) and n == sorted(n)
        assert not has_triple(n)
        assert tuple(n) not in service.history and res["never_drawn_before"]
    assert client.get("/api/losuj", params={"count": 11}).status_code == 422
    assert client.post("/api/losuj", json={"strength": -1}).status_code == 422


def test_losuj_on_fake_history(fake_draws):
    svc = LottoService(fake_draws)
    assert svc.meta()["draws"] == 5
    assert len(svc.losuj(count=3, seed=1)) == 3


def test_ranges():
    assert _ranges([1, 2, 3, 7, 9, 10]) == [[1, 3], [7, 7], [9, 10]]


def test_static_site_data_up_to_date():
    """web/data musi odpowiadać bazie — inaczej uruchom: python scripts/build_static.py"""
    data = ROOT / "web" / "data"
    assert (data / "draws.csv").read_bytes() == (ROOT / "data" / "lotto_normalized.csv").read_bytes()
    stats = json.loads((data / "stats.json").read_text(encoding="utf-8"))
    assert stats == json.loads(json.dumps(service.stats, ensure_ascii=False))
    draws = json.loads((data / "draws.json").read_text(encoding="utf-8"))
    assert len(draws["rows"]) == len(service.draws)


def test_filters_endpoints():
    info = client.get("/api/filters").json()
    assert [f["no"] for f in info["filters"]] == list(range(1, 13))
    est = client.get("/api/filters/estimate", params={"filters": "suma,parzyste"}).json()
    assert 50 < est["kept_pct"] < 90 and est["precise"]
    assert client.get("/api/filters/estimate", params={"filters": "pary,podobne"}).status_code == 422
    r = client.get("/api/losuj", params={"filters": "suma,parzyste,popularne"}).json()
    n = r["results"][0]["numbers"]
    assert 100 <= sum(n) <= 200 and 2 <= sum(x % 2 == 0 for x in n) <= 4 and max(n) > 31
    assert r["filters"]["filters"] == ["suma", "parzyste", "popularne"]
    body = {"filters": ["podobne"], "similar_min": 5}
    assert client.post("/api/losuj", json=body).status_code == 200
    assert client.post("/api/losuj", json={"filters": ["xyz"]}).status_code == 422


def test_static_filters_json_up_to_date():
    data = json.loads((ROOT / "web" / "data" / "filters.json").read_text(encoding="utf-8"))
    assert data == json.loads(json.dumps(service.filters_info, ensure_ascii=False))
