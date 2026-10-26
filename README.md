# Lotto — analiza statystyk

Aplikacja lokalna (Python + Streamlit) do analizy historii losowań Lotto z pliku CSV.
Oblicza, które liczby padały najczęściej i najrzadziej, porównuje okresy, wykrywa błędy w danych
i jest przygotowana na późniejsze podłączenie API. **Nie przewiduje wyników** — przy prawidłowym losowaniu
każda liczba 1–49 ma w następnym losowaniu taką samą szansę, niezależnie od historii.

## Instalacja (krok po kroku, bez doświadczenia programistycznego)

1. Zainstaluj Pythona 3.11 lub nowszego ze strony python.org (na Windows zaznacz „Add Python to PATH").
2. Otwórz terminal (Windows: „Wiersz polecenia" lub PowerShell) i wejdź do folderu projektu:
   `cd ścieżka\do\lotto_stats`
3. Utwórz środowisko i zainstaluj biblioteki:
   ```
   python -m venv .venv
   .venv\Scripts\activate          (macOS/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   ```

## Uruchomienie

```
streamlit run app.py
```
Przeglądarka otworzy się pod adresem http://localhost:8501. Zatrzymanie: `Ctrl+C` w terminalu.

## Widoki

Dashboard · Statystyki liczb · Porównanie okresów · **Pary i trójki** · Historia losowań · Import i jakość danych · Konfiguracja i aktualizacja.
Okres analizy: cała historia, ostatni miesiąc (od dziś), ostatni miesiąc danych w bazie lub własny zakres dat.
Eksporty (CSV/XLSX) zawsze odpowiadają widocznemu okresowi.

## Pary i trójki

Widok **Pary i trójki** pokazuje, które pary (2 liczby) i trójki (3 liczby) padały razem najczęściej, dla wybranego okresu:
- TOP N (5–30) z oczekiwaną liczbą wystąpień, datą ostatniego wystąpienia i liczbą losowań od ostatniego. Remis na granicy TOP nie jest rozstrzygany arbitralnie — pokazywane są wszystkie kombinacje z tym samym wynikiem (do 50 wierszy).
- **Czy lider jest zaskakujący?** — porównanie z liderem w 300 symulacjach czysto losowych danych o tej samej liczbie losowań (ziarno stałe, wynik powtarzalny). Ranking zawsze ma lidera, więc to właściwy punkt odniesienia, a nie średnia.
- Wyszukiwarka dowolnej pary/trójki: liczba wystąpień, pozycja, trend roczny (wystąpienia vs oczekiwane), lista losowań.
- Eksport CSV dla widocznego okresu. Kombinacje, które nie padły ani razu, nie są wypisywane (dla trójek to kilka tysięcy wierszy) — widok podaje ich liczbę.

Przy 6 z 49 każda konkretna para ma w jednym losowaniu prawdopodobieństwo 15/1176 ≈ 1,3%, a każda trójka 20/18 424 ≈ 0,11%. Historyczne częstości nie są prognozą.
Kod: `src/combinations.py` (bez zależności od interfejsu).

## Baza danych i aktualizacja CSV

Baza: `data/lotto_normalized.csv`, kolumny `draw_id, draw_date (RRRR-MM-DD), n1…n6`.
Aby dodać dane (np. nowszy plik z historią losowań):
1. Widok **Import i jakość danych** → wgraj CSV lub XLSX (separator `,` `;` lub tabulator; kodowanie UTF-8 / Windows-1250;
   kolumny nazwane `nr/data` + sześć kolumn z liczbami, albo `draw_id, draw_date, n1…n6`).
2. Sprawdź raport. Rekordy błędne **nie są usuwane po cichu** — są wypisane do ręcznej weryfikacji.
3. Wybierz „Dołącz tylko nowe losowania" (bez duplikatów) lub „Zastąp całą bazę" i kliknij **Zastosuj**.
   Przed każdą zmianą powstaje kopia `data/lotto_normalized.bak-RRRRMMDD-GGMMSS.csv`. Oryginalne pliki nigdy nie są nadpisywane.

Konwersja z linii poleceń: `python -m src.normalizer plik.xlsx data/lotto_normalized.csv reports/raport.md`

## Testy

```
python -m pytest tests -q
```
Testy używają **sztucznych** danych (nie są prawdziwymi wynikami Lotto).

## Struktura

`app.py` (interfejs) · `src/normalizer.py` (odczyt i walidacja) · `src/data_loader.py` · `src/statistics_engine.py` (obliczenia, bez UI) · `src/combinations.py` (pary i trójki) ·
`src/data_sources.py` (`LotteryDataSource`: `CsvDataSource`, `ExcelDataSource`, `ApiDataSource`) · `src/sync.py` (bezpieczne scalanie) ·
`src/api_client.py` · `src/exporter.py` · `tests/` · `data/` · `reports/`

## API — co wymaga uzupełnienia

Nic z API nie jest zgadywane. Aplikacja działa w pełni bez klucza; przycisk „Odśwież z API" jest wtedy nieaktywny.
Gotowe: konfiguracja ze zmiennych `LOTTO_API_BASE_URL`, `LOTTO_API_KEY` (plik `.env` lub środowisko; klucz nie trafia do logów ani CSV),
timeouty, ponawianie przy błędach sieci i 5xx, obsługa HTTP 429, walidacja przed zapisem, aktualizacja idempotentna i atomowa.
**Do potwierdzenia w dokumentacji dostawcy** (miejsca `TODO(API)` w `src/api_client.py`):
1. czy publiczne API w ogóle istnieje i na jakich warunkach;
2. adres bazowy i endpoint(y) listy losowań;
3. sposób autoryzacji (`_auth_headers`);
4. parametry filtrowania „tylko nowe" i paginacja (`fetch_raw`);
5. schemat odpowiedzi → format kanoniczny (`map_api_record`).

## Znane ograniczenia

- Dane w repozytorium kończą się 2015-06-04 — dlatego „ostatni miesiąc (od dziś)" jest pusty; użyj „ostatni miesiąc danych w bazie" albo uzupełnij historię.
- Obsługiwane tylko Lotto 6 z 49 (zakres 1–49, 6 różnych liczb). Mini Lotto, Multi Multi itp. wymagają osobnej konfiguracji.
- Daty rozpoznawane w formatach RRRR-MM-DD, DD-MM-RRRR, DD.MM.RRRR, DD/MM/RRRR (kolejność dzień-miesiąc zgodna z polskim zapisem).
- Brak automatycznego harmonogramu synchronizacji (celowo: najpierw ręczne odświeżanie).

## Możliwe usprawnienia

Uzupełnienie historii 2015–dziś, automatyczny harmonogram po potwierdzeniu API, obsługa innych gier, logowanie użytkowników przy uruchomieniu na serwerze.
