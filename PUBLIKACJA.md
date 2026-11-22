# Jak opublikować Losuj6

Projekt ma dwie części do publikacji:

| Część | Co to jest | Gdzie | Koszt |
|---|---|---|---|
| **Strona „Arcade 49”** (`web/`) | publiczna strona: bęben z kulkami, generator, karty 49 liczb, rankingi, pobieranie bazy | **Cloudflare Workers** (static assets) | 0 zł |
| **API** (`api/`) | FastAPI: historia losowań, statystyki i generator „Losuj 6 v 0.1” (`src/generator.py`) | **Render** (plan Free) | 0 zł |
| Panel Streamlit (`app.py`) | Twoje narzędzie do importu i kontroli danych | lokalnie albo Streamlit Cloud (niżej) | 0 zł |

Strona statyczna działa zawsze. Statystyki i pliki do pobrania (`web/data/`) są w niej zapisane,
więc nie czekają na serwer. Na API czeka tylko przycisk **Losuj 6** i zapytania do `/api/…`.

## 1. API na Render

1. Zaloguj się na **https://dashboard.render.com** i połącz konto GitHub z repozytorium `Kyoshi84/Losuj6`.
2. Kliknij **New → Blueprint**, wybierz repozytorium i gałąź `main`.
   Render przeczyta plik `render.yaml` i pokaże usługę **losuj6-api** (plan Free, region Frankfurt).
3. Kliknij **Apply** (lub **Deploy Blueprint**). Budowanie trwa kilka minut.
4. Po wdrożeniu skopiuj adres usługi, np. `https://losuj6-api.onrender.com`. Jeśli nazwa była zajęta,
   Render doda do niej końcówkę: użyj dokładnie tego adresu, który pokazuje panel.
5. Sprawdź w przeglądarce:
   - `https://TWOJ-ADRES.onrender.com/api/health`: powinno pokazać `"status":"ok"` i liczbę losowań,
   - `https://TWOJ-ADRES.onrender.com/docs`: interaktywna dokumentacja API.

Bez Blueprintu: **New → Web Service** → repozytorium, a potem:
- **Build command:** `pip install -r requirements-api.txt`
- **Start command:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- **Health check path:** `/api/health`
- zmienna środowiskowa `PYTHON_VERSION` = `3.12.8`

**Darmowy plan usypia API** po ok. 15 minutach bez ruchu. Pierwsze zapytanie po przerwie trwa 30–60 s.
Strona sama „budzi” API zaraz po wejściu użytkownika i pokazuje komunikat, jeśli trzeba poczekać.

## 2. Wpisz adres API do strony

W pliku `web/config.js` ustaw adres z kroku 1:

```js
window.LOSUJ6_CONFIG = {
  apiBase: "https://TWOJ-ADRES.onrender.com",
};
```

Zatwierdź i wypchnij zmianę (`git commit`, `git push`).

## 3. Strona na Cloudflare (Workers)

1. Zaloguj się na **https://dash.cloudflare.com** → **Workers & Pages** → **Create** → **Import a repository**
   i wybierz repozytorium `Kyoshi84/Losuj6`.
2. Ustawienia:
   - **Project name:** `losuj6`
   - **Build command:** zostaw puste
   - **Deploy command:** `npx wrangler deploy`
   - **Production branch:** `main`
3. Kliknij **Deploy**. Plik `wrangler.toml` mówi Cloudflare, żeby opublikował katalog `web/` jako stronę statyczną.
   Strona będzie pod adresem `https://losuj6.<twoja-subdomena>.workers.dev`. Każdy `git push` na `main` aktualizuje ją automatycznie.
4. Własna domena (opcjonalnie): w projekcie **Settings → Domains & Routes → Add → Custom domain**.

Plik `web/_headers` ustawia nagłówki: pliki z `web/data/` można pobierać także z innych stron (CORS),
a `draws.csv` pobiera się jako plik.

## 4. Ogranicz API do swojej strony (opcjonalnie)

Domyślnie API odpowiada każdej stronie (`ALLOWED_ORIGINS="*"`), bo to publiczne dane tylko do odczytu.
Jeśli wolisz, żeby generator działał tylko na Twojej stronie, w Render → **losuj6-api → Environment** ustaw:

```
ALLOWED_ORIGINS = https://losuj6.twoja-subdomena.workers.dev,https://twoja-domena.pl
```

Działa to tylko w przeglądarkach. Wywołania z `curl` czy skryptów nadal przechodzą.

## 5. Aktualizacja wyników

Po każdej zmianie bazy `data/lotto_normalized.csv` (import nowych losowań):

```bash
python scripts/build_static.py      # odświeża web/data/ (statystyki i pliki do pobrania)
python -m pytest -q                 # test pilnuje, że web/data zgadza się z bazą
git add data web/data && git commit -m "Nowe losowania" && git push
```

Render i Cloudflare same pobiorą zmiany z `main` i wdrożą nową wersję.

## Podgląd lokalny

```bash
pip install -r requirements.txt
uvicorn api.main:app --port 8000                  # API: http://127.0.0.1:8000/docs
cd web && python -m http.server 8080              # strona w drugim terminalu
```

Otwórz `http://127.0.0.1:8080/?api=http://127.0.0.1:8000`. Parametr `?api=` podmienia adres z `config.js`.

## Endpointy API

| Metoda | Adres | Opis |
|---|---|---|
| GET | `/api/health` | stan serwera i liczba losowań |
| GET | `/api/meta` | zakres bazy, luki w numeracji |
| GET | `/api/draws` | historia; filtry `year`, `from`, `to`, `order`, `limit`, `offset`, `format=csv` |
| GET | `/api/draws/latest` | ostatnie losowanie |
| GET | `/api/draws/{nr}` | losowanie o numerze |
| GET | `/api/stats` | statystyki 49 liczb (z `from`/`to` dla wybranego okresu) |
| GET | `/api/stats/{liczba}` | statystyki jednej liczby |
| GET/POST | `/api/losuj` | generator „Losuj 6 v 0.1”; `strength` 0–5, `count` 1–10, `filters` (np. `suma,parzyste`), `similar_min` 4 lub 5 |
| GET | `/api/filters` | 12 filtrów trybu ekspert: opis, wykluczenia, ile kombinacji zostaje |
| GET | `/api/filters/estimate` | ile kombinacji zostaje po włączeniu kilku filtrów naraz |

Filtry (tryb ekspert) opisuje `src/filters.py`. Pary i trójki (1, 2) nie łączą się z filtrem „Bez podobnych do historii” (10),
bo mają przeciwne cele. Po zmianie bazy `python scripts/build_static.py` odświeża też `web/data/filters.json`.

---

# Panel Streamlit (opcjonalnie)

## Stan bazy

Baza `data/lotto_normalized.csv` kończy się na losowaniu z **2026-11-17** (7311 losowań: numery 1–4355 z lat 1957–2006 oraz 4477–7432 z lat 2008–2026; brakuje tylko losowań 4356–4476 z roku 2007).
Statystyki, strona i generator opierają się na tych danych: brakujący rok 2007 nie jest liczony
do częstości, a jego kombinacje nie są wykluczane przez generator.

Uzupełnij bazę lokalnie (widok **Import i jakość danych**: wgraj plik CSV/XLSX z pełną historią),
uruchom `python scripts/build_static.py`, a potem zatwierdź `data/lotto_normalized.csv` i `web/data/` i wypchnij go do GitHub (`git add`, `git commit`, `git push`).
Na serwerze wgrywaj dane tylko do testów (patrz „Ważne ograniczenia”).

## Wariant A: Streamlit Community Cloud (za darmo)

1. Wejdź na **https://share.streamlit.io** i zaloguj się kontem GitHub (tym samym, które ma dostęp do repozytorium `Kyoshi84/Losuj6`).
   Przy pierwszym logowaniu zgódź się, żeby Streamlit czytał Twoje repozytoria (dotyczy to też prywatnych).
2. Kliknij **Create app**, a potem **Deploy a public app from GitHub** (lub „Yup, I have an app”).
3. Wypełnij formularz:
   - **Repository:** `Kyoshi84/Losuj6`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** wybierz nazwę, np. `losuj6` (adres będzie wyglądał tak: `https://losuj6.streamlit.app`)
4. Otwórz **Advanced settings**:
   - **Python version:** 3.12 lub 3.13 (aplikacja wymaga co najmniej 3.11),
   - **Secrets:** zostaw puste, chyba że masz dostęp do API wyników (patrz niżej).
5. Kliknij **Deploy**. Pierwsze uruchomienie trwa kilka minut, bo instalowane są biblioteki z `requirements.txt`.
6. Gotowe. Każdy `git push` na `main` automatycznie aktualizuje aplikację.

### Kto widzi aplikację

W ustawieniach aplikacji (**⋮ → Settings → Sharing**) wybierasz, czy aplikacja jest dostępna dla wszystkich,
czy tylko dla osób zaproszonych e-mailem. Jeśli repozytorium jest prywatne, aplikacja domyślnie też jest prywatna.

### Klucz API (opcjonalnie)

Jeśli masz dostęp do API wyników Lotto, **nie wpisuj klucza do repozytorium**. W **⋮ → Settings → Secrets** wklej:

```toml
LOTTO_API_BASE_URL = "https://adres-api"
LOTTO_API_KEY = "twój-klucz"
```

Streamlit udostępnia te wartości aplikacji jako zmienne środowiskowe, czyli tak samo jak lokalny plik `.env`.

## Ważne ograniczenia hostingu

- **Zmiany bazy na serwerze nie są trwałe.** Import pliku i synchronizacja z API zapisują dane na dysku serwera,
  a ten dysk jest czyszczony przy każdym restarcie lub aktualizacji aplikacji (a nieużywana aplikacja jest usypiana).
  Na stałe zmieniasz bazę tylko lokalnie, a potem robisz commit i push pliku `data/lotto_normalized.csv`.
- **Każdy, kto otworzy aplikację, może podmienić bazę** w widoku „Import i jakość danych”, do najbliższego restartu.
  Jeśli aplikacja ma być publiczna, ogranicz dostęp do zaproszonych osób albo poproś o wersję z wyłączonym importem na serwerze.
- Aplikacja usypia się po kilku dniach bez wizyt. Pierwsze wejście po przerwie wybudza ją, co trwa około minuty.

## Wariant B: własny serwer lub inny hosting (Render, Railway, VPS)

Wystarczy dowolna maszyna z Pythonem 3.11+:

```bash
git clone https://github.com/Kyoshi84/Losuj6.git
cd Losuj6
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
```

Na usługach typu Render lub Railway:
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`

Klucz API ustaw tam jako zmienne środowiskowe `LOTTO_API_BASE_URL` i `LOTTO_API_KEY`.
Ograniczenie o nietrwałym dysku dotyczy też tych usług, chyba że dokupisz trwały dysk
i wskażesz na nim bazę zmienną `LOTTO_DATA_PATH`.

## Sprawdzenie przed publikacją

```bash
pip install -r requirements.txt
python -m pytest -q        # powinno być: 99 passed
streamlit run app.py       # sprawdź lokalnie widoki i przycisk „Losuj 6 v 0.1”
```
