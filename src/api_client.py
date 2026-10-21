"""Szkielet integracji z API Lotto.

UWAGA: adres API, parametry, schemat odpowiedzi i sposób autoryzacji NIE są znane ani potwierdzone.
Nic tu nie jest zgadywane. Warstwa transportowa (timeouty, ponowienia, obsługa błędów HTTP i limitów)
jest gotowa; to, co wymaga potwierdzenia z dokumentacji dostawcy, oznaczono `TODO(API)`.
Klucz API jest czytany wyłącznie ze zmiennej środowiskowej i nigdy nie trafia do logów.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


class ApiError(Exception):
    """Błąd komunikacji z API (HTTP, sieć, limit zapytań)."""


class ApiNotConfiguredError(ApiError):
    """Brak LOTTO_API_BASE_URL lub LOTTO_API_KEY. Aplikacja działa dalej na CSV."""


class ApiNotImplementedError(ApiError):
    """Element integracji czeka na potwierdzenie specyfikacji API."""


@dataclass(frozen=True)
class ApiConfig:
    base_url: str | None
    api_key: str | None
    timeout: float = 15.0
    max_retries: int = 3
    backoff: float = 1.0

    @classmethod
    def from_env(cls) -> "ApiConfig":
        return cls(
            base_url=os.getenv("LOTTO_API_BASE_URL") or None,
            api_key=os.getenv("LOTTO_API_KEY") or None,
            timeout=float(os.getenv("LOTTO_API_TIMEOUT", "15")),
            max_retries=int(os.getenv("LOTTO_API_RETRIES", "3")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def __repr__(self) -> str:  # nie ujawniaj klucza w logach / tracebackach
        return f"ApiConfig(base_url={self.base_url!r}, api_key={'***' if self.api_key else None}, timeout={self.timeout})"


class LottoApiClient:
    def __init__(self, config: ApiConfig | None = None, sleep: Callable[[float], None] = time.sleep):
        self.config = config or ApiConfig.from_env()
        self._sleep = sleep

    def status(self) -> str:
        if not self.config.configured:
            return "nieskonfigurowane (brak LOTTO_API_BASE_URL / LOTTO_API_KEY)"
        return "skonfigurowane, ale mapowanie odpowiedzi czeka na potwierdzenie specyfikacji API"

    # ---- transport (gotowy) -------------------------------------------------
    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.config.configured:
            raise ApiNotConfiguredError("API nie jest skonfigurowane.")
        import requests

        url = self.config.base_url.rstrip("/") + "/" + path.lstrip("/")
        headers = self._auth_headers()
        last: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.config.timeout)
            except requests.RequestException as e:  # sieć, timeout
                last = e
                log.warning("API: błąd sieci (próba %s/%s): %s", attempt, self.config.max_retries, type(e).__name__)
            else:
                if resp.status_code == 429:  # limit zapytań
                    wait = float(resp.headers.get("Retry-After", self.config.backoff * attempt))
                    last = ApiError("HTTP 429 (limit zapytań)")
                    self._sleep(min(wait, 60))
                    continue
                if 500 <= resp.status_code < 600:
                    last = ApiError(f"HTTP {resp.status_code}")
                elif resp.status_code >= 400:
                    raise ApiError(f"HTTP {resp.status_code} — żądanie odrzucone (bez ponawiania)")
                else:
                    try:
                        return resp.json()
                    except ValueError as e:
                        raise ApiError("Odpowiedź API nie jest poprawnym JSON-em.") from e
            self._sleep(self.config.backoff * attempt)
        raise ApiError(f"API niedostępne po {self.config.max_retries} próbach: {last}")

    def _auth_headers(self) -> dict[str, str]:
        # TODO(API): potwierdzić sposób autoryzacji (nagłówek, schemat, nazwa pola).
        raise ApiNotImplementedError("Sposób autoryzacji API nie został potwierdzony.")

    # ---- do uzupełnienia po uzyskaniu dokumentacji ---------------------------
    def fetch_raw(self, after_draw_id: int | None = None) -> list[dict[str, Any]]:
        # TODO(API): potwierdzić endpoint, parametry (np. filtr po numerze/dacie) i paginację.
        raise ApiNotImplementedError("Endpoint pobierania losowań nie został potwierdzony.")


def map_api_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Mapowanie rekordu API → format kanoniczny {draw_id, draw_date, n1..n6}.

    TODO(API): uzupełnić po poznaniu schematu odpowiedzi. Celowo bez domyślnych założeń.
    """
    raise ApiNotImplementedError("Mapowanie odpowiedzi API nie zostało zdefiniowane.")
