# Jak opublikować aplikację Losuj6

Aplikacja to program Streamlit (`app.py`). Najprostszy sposób, żeby była dostępna pod adresem w internecie,
to darmowy **Streamlit Community Cloud**, który uruchamia aplikację prosto z repozytorium GitHub.

## Zanim zaczniesz: zaktualizuj bazę

Baza `data/lotto_normalized.csv` kończy się na losowaniu z **2025-12-30** (3549 losowań: numery 1–731 z lat 1957–1970 oraz 4477–7294 z lat 2008–2025; brakuje losowań 732–4476 z lat 1971–2007).
Statystyki i generator „Losuj 6” działają poprawnie, ale opierają się na tych starych danych:
- liczby „najczęstsze” to najczęstsze w latach 1957–1970 i 2008–2025,
- generator wyklucza tylko kombinacje z tego okresu.

Uzupełnij bazę lokalnie (widok **Import i jakość danych**: wgraj plik CSV/XLSX z pełną historią),
a potem zatwierdź zmieniony plik `data/lotto_normalized.csv` i wypchnij go do GitHub (`git add`, `git commit`, `git push`).
Na serwerze wgrywaj dane tylko do testów (patrz „Ważne ograniczenia”).

## Wariant A: Streamlit Community Cloud (zalecany, za darmo)

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
python -m pytest -q        # powinno być: 80 passed
streamlit run app.py       # sprawdź lokalnie widoki i przycisk „Losuj 6 v 0.1”
```
