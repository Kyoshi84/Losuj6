"""Publiczne API Losuj6 (tylko odczyt + generator „Losuj 6 v 0.1”).

Uruchomienie lokalne:  uvicorn api.main:app --reload
Dokumentacja:          http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import datetime as dt
import io
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from src import generator

from .service import DB_PATH, NUM_COLS, LottoService, draw_to_dict

MAX_COUNT = 10
MAX_STRENGTH = 5.0

service = LottoService.from_csv(os.environ.get("LOSUJ6_DB") or DB_PATH)

app = FastAPI(
    title="Losuj6 API",
    version=generator.VERSION,
    description=(
        "Historia losowań 6 z 49 (od 1957 r.), statystyki liczb i generator „Losuj 6 v 0.1”.\n\n"
        "Generator: wagi liczb rosną z liczbą wystąpień, pomija kombinacje, które już padły, "
        "i nie dopuszcza 3 kolejnych liczb.\n\n"
        "**Uwaga:** historyczne częstości nie są prognozą — każda kombinacja ma tę samą szansę.\n\n"
        "Projekt niezależny, niezwiązany z Totalizatorem Sportowym."
    ),
)

_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"],
                   allow_headers=["*"], max_age=86400)
app.add_middleware(GZipMiddleware, minimum_size=1024)

CACHE = {"Cache-Control": "public, max-age=600"}


# ---------------------------------------------------------------- modele
class LosujRequest(BaseModel):
    strength: float = Field(1.0, ge=0, le=MAX_STRENGTH,
                            description="Wpływ statystyk: 0 = równomiernie, 1 = waga ∝ wystąpienia+1, 2 = kwadrat…")
    count: int = Field(1, ge=1, le=MAX_COUNT, description="Ile zestawów wylosować")


# ---------------------------------------------------------------- endpointy
@app.get("/", include_in_schema=False)
def root():
    return {"name": "Losuj6 API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", tags=["system"])
def health():
    m = service.meta()
    return {"status": "ok", "draws": m["draws"], "last_date": m.get("last_date"),
            "generator_version": generator.VERSION}


@app.get("/api/meta", tags=["losowania"])
def meta():
    return JSONResponse(service.meta(), headers=CACHE)


@app.get("/api/draws", tags=["losowania"])
def draws(
    year: int | None = Query(None, ge=1957, le=2100, description="Tylko losowania z danego roku"),
    date_from: dt.date | None = Query(None, alias="from", description="Od daty (RRRR-MM-DD)"),
    date_to: dt.date | None = Query(None, alias="to", description="Do daty (RRRR-MM-DD)"),
    order: Literal["asc", "desc"] = Query("asc"),
    limit: int | None = Query(None, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
    format: Literal["json", "csv"] = Query("json"),
):
    """Historia losowań. Bez parametrów zwraca całą bazę."""
    d = service.filter(year=year, date_from=date_from, date_to=date_to)
    if order == "desc":
        d = d.iloc[::-1]
    total = len(d)
    d = d.iloc[offset: offset + limit if limit else None]
    if format == "csv":
        buf = io.StringIO()
        out = d[["draw_id", "draw_date", *NUM_COLS]].copy()
        out["draw_date"] = out["draw_date"].dt.date
        out.to_csv(buf, index=False)
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={**CACHE, "Content-Disposition": 'attachment; filename="losuj6_draws.csv"'})
    return JSONResponse({"total": total, "offset": offset, "count": len(d),
                         "draws": [draw_to_dict(r) for r in d.itertuples()]}, headers=CACHE)


@app.get("/api/draws/latest", tags=["losowania"])
def latest():
    r = service.latest()
    if r is None:
        raise HTTPException(404, "Baza jest pusta")
    return JSONResponse(r, headers=CACHE)


@app.get("/api/draws/{draw_id}", tags=["losowania"])
def by_id(draw_id: int):
    r = service.by_id(draw_id)
    if r is None:
        raise HTTPException(404, f"Brak losowania nr {draw_id}")
    return JSONResponse(r, headers=CACHE)


@app.get("/api/stats", tags=["statystyki"])
def stats(
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
):
    """Statystyki 49 liczb: wystąpienia, ranking, klasa „postaci”, forma w ostatnich 100 losowaniach,
    częstość w dekadach, TOP 10 najczęstszych/najrzadszych i test χ² równomierności."""
    if date_from is None and date_to is None:
        return JSONResponse(service.stats, headers=CACHE)
    d = service.filter(date_from=date_from, date_to=date_to)
    if d.empty:
        raise HTTPException(404, "Brak losowań w podanym okresie")
    return JSONResponse(service.build_stats(d), headers=CACHE)


@app.get("/api/stats/{number}", tags=["statystyki"])
def number_stats(number: int):
    if not 1 <= number <= 49:
        raise HTTPException(422, "Liczba musi być z zakresu 1–49")
    return JSONResponse(service.stats["numbers"][number - 1], headers=CACHE)


@app.post("/api/losuj", tags=["generator"])
def losuj_post(req: LosujRequest):
    """Generator „Losuj 6 v 0.1”."""
    return _losuj(req.strength, req.count)


@app.get("/api/losuj", tags=["generator"])
def losuj_get(strength: float = Query(1.0, ge=0, le=MAX_STRENGTH),
              count: int = Query(1, ge=1, le=MAX_COUNT)):
    """To samo co POST — wygodne do wywołania z przeglądarki."""
    return _losuj(strength, count)


def _losuj(strength: float, count: int):
    try:
        results = service.losuj(strength=strength, count=count)
    except generator.GeneratorError as e:
        raise HTTPException(503, str(e)) from e
    return JSONResponse({"generator": generator.BUTTON_LABEL, "strength": strength, "results": results},
                        headers={"Cache-Control": "no-store"})
