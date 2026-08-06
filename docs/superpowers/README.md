# Rejestr realizacji programu Superpowers

Stan aktualizowany: 2026-08-05

Ten plik jest operacyjnym rejestrem realizacji planów z katalogu
`docs/superpowers/plans`. Po ukończeniu każdego zadania wpisywane są tu
wynik, zakres weryfikacji i ewentualne ograniczenia. Prefiks `V =` przy planie
oznacza pakiet wykonany przed rozpoczęciem tego rejestru.

## Legenda

| Stan | Znaczenie |
| --- | --- |
| Nie ruszono | Nie rozpoczęto pracy ani zmian w kodzie dla zadania. |
| W toku | Zadanie jest aktywnie realizowane; wynik nie został jeszcze potwierdzony testami. |
| Ukończono | Zmiana i wymagane dla zadania testy zostały wykonane. |
| Zablokowane | Praca nie może bezpiecznie postąpić bez decyzji lub zmiany zewnętrznej. |

## Pakiety wykonane wcześniej

| Pakiet | Stan | Źródło |
| --- | --- | --- |
| 1. SQLite lifecycle i telemetria | Ukończono | `plans/V = 2026-07-27-sqlite-lifecycle-and-telemetry.md` |
| 2. Wyszukiwanie produktów i start desktopu | Ukończono | `plans/V = 2026-07-27-product-query-and-desktop-startup.md` |
| 6. Procesy w tle, polling i aktywni klienci | Ukończono | `plans/V = 2026-07-27-background-runtime-and-polling.md` |

## Pakiet 3 — Upload, obrazy i kolejka

Plan: `plans/2026-07-27-upload-image-processing-and-queue.md`

| Zadanie | Stan | Wynik / następny krok |
| --- | --- | --- |
| 1. Ograniczona `ProcessQueueService` | Ukończono | Dodano rezerwacje globalne/per użytkownik, FIFO workerów, pozycje, anulowanie oczekującego zadania i kontrolowane zamknięcie. Zweryfikowano: `tests/test_process_queue.py` — 2 passed. |
| 2. Rezerwacja przed stagingiem i bezpieczny staging | Ukończono | Dodano `UploadStagingService` ze strumieniowaniem 1 MiB, limitem, cleanupem oraz wykonaniem walidacji i AV poza event loopem. Walidacja obrazu, sygnatury i rdzeń Defendera zostały wydzielone z `web/app.py`; adaptery zachowują konfigurację i historię wyników skanu. Raw staged pliki są odrzucane przez resolver tokenów. Zweryfikowano: 27 passed, 20 subtests. |
| 3. Jeden końcowy `ImagePipeline` | Ukończono | Dodano atomowy `ImagePipeline` z pojedynczym otwarciem źródła, usuwaniem EXIF i ograniczonym do 6 prób wyszukiwania jakości. Web i desktop delegują końcowy zapis rasterów do pipeline'u; dokumenty nadal są kopiowane bez przetwarzania. Zweryfikowano: 122 passed, 12 istniejących ostrzeżeń FastAPI, 43 subtests. |
| 4. Wspólna kolejka foreground/background | Ukończono | Endpointy foreground i background rezerwują po `cache_scope` przed odczytem formularza, a następnie używają jednej `ProcessQueueService`. Pełna kolejka zwraca `429` z `Retry-After`; foreground czeka na końcowy wynik tego samego joba. Zweryfikowano: 18 testów kolejki/route/job oraz test health procesora; kompilacja i `git diff --check`. |
| 5. Anulowanie i bezpieczny cleanup | Ukończono | Dodano endpoint `DELETE /api/process-jobs/{job_id}`, współpracujący token anulowania między etapami oraz bezpieczny root `job-*`. Cleanup usuwa staging po sukcesie, błędzie i anulowaniu, odrzuca ścieżki poza rootem i okresowo usuwa tylko nieaktywne katalogi starsze niż 24 h. Zweryfikowano: 99 passed, 12 istniejących ostrzeżeń FastAPI, 20 subtests; kompilacja i `git diff --check`. |
| 6. Benchmark event loopa i pipeline'u | Ukończono | Dodano deterministyczny benchmark 26 obrazów: p95 `/api/health`, głębokość kolejki, peak pamięci i liczba kodowań JPEG. Ostatni pomiar: p95 19,25 ms, peak 1 023 477 B, głębokość 1 i maksymalnie 6 kodowań JPEG. Zweryfikowano: 1214 passed, 20 istniejących ostrzeżeń FastAPI, 66 subtests; kompilacja i `git diff --check`. |

## Pakiet 4 — FTP i indeks plików

Plan: `plans/2026-07-27-ftp-and-file-indexing.md`

| Zadanie | Stan | Wynik / następny krok |
| --- | --- | --- |
| 1. Procesowy cache listingu z singleflight | Ukończono | Dodano lokalny cache FTP z TTL 60 s, HMAC-owym kluczem bez sekretów, singleflight per lokalizacja i fallbackiem do ostatniego kompletnego snapshotu po błędzie refreshu. Potwierdzone uploady/delete mogą aktualizować snapshot natychmiast, a `invalidate` wymusza kolejny refresh. Zweryfikowano: 4 passed; kompilacja i `git diff --check`. |
| 2. Selektywne `NLST` z capability i fallbackiem | Ukończono | Dodano trójstan capability (`unknown`/`supported`/`unsupported`) dla targeted `NLST EAN_*`. Odpowiedź jest ponownie filtrowana parserem slotów; pusta odpowiedź przy `unknown` i błąd wildcarda wymuszają pełny listing, który jest cache’owany. Świeży pełny snapshot omija nowe połączenie FTP. Zweryfikowano: 14 passed; kompilacja i `git diff --check`. |
| 3. Invalidacja cache po synchronizacji FTP | Ukończono | Po potwierdzonym `STOR` snapshot dostaje nową nazwę, a po `DELE` traci usuniętą; tylko potwierdzone komendy zmieniają cache. Szeroki błąd w częściowej synchronizacji unieważnia go przed zwróceniem wyniku błędu. Zweryfikowano: 29 passed, 77 deselected, 4 istniejące ostrzeżenia FastAPI; kompilacja i `git diff --check`. |
| 4. Start lokalnego indeksu bez automatycznego pełnego skanu | Ukończono | `LocalFileIndex` ocenia wersję, kanoniczny root i poprawny UTC timestamp z TTL 15 min; świeży snapshot nie uruchamia workera. Desktop i web używają warunkowego startu, a przyciski ręczne oraz zapis produktu wymuszają refresh. Zweryfikowano: 11 passed, 161 deselected, 4 istniejące ostrzeżenia FastAPI; kompilacja i `git diff --check`. |
| 5. Jedna segmentowa reprezentacja SQLite | Ukończono | Zastąpiono blob aktywną, kompletną generacją segmentów SQLite. Migracja legacy zapisuje segmenty i metadane atomowo, oznacza generację jako kompletną, a następnie usuwa blob; odczyt rekonstruuje snapshot z segmentów. Zweryfikowano: 53 passed; kompilacja i `git diff --check`. |
| 6. Przyrostowe odświeżanie segmentów | Ukończono | Indeks porównuje metadane katalogów i parsuje pliki tylko w zmienionych segmentach; niepewny fingerprint wymusza pełny skan. SQLite kopiuje niezmienione segmenty atomowo przez `INSERT … SELECT`, a awaria pozostawia poprzednią kompletną generację aktywną. Zweryfikowano: 14 passed, 45 deselected; kompilacja i `git diff --check`. |
| 7. Zarządzany lifecycle temp FTP | Ukończono | Dodano bezpieczny manager katalogów requestowych FTP: kanonizację ścieżek, ochronę przed usuwaniem poza rootem, TTL dla nieaktywnych katalogów i zamknięcie przy `App.destroy`. Kolejny lookup anuluje poprzedni transfer między plikami; nieaktualne preview jest zwalniane po zakończeniu workera. Zweryfikowano: 37 passed, 14 subtests; kompilacja i `git diff --check`. |
| 8. Usunięcie nieaktywnych indeksów i benchmark | Ukończono | Po potwierdzeniu braku importów runtime usunięto `file_index_service.py` i `directory_index_service.py`. Dodano benchmarki regresyjne: 100 000 nazw FTP z jednym pełnym listingiem w TTL oraz 10 000 segmentów z 1% zmian (100 skanowanych, 9 900 kopiowanych, jedna aktywna generacja SQLite). Zweryfikowano: 81 testów pakietu; pełna regresja 1247 passed, 20 istniejących ostrzeżeń FastAPI, 66 subtests; kompilacja i `git diff --check`. |

## Pakiet 5 — Integracje SQL, Pimcore i tłumaczenia

Plan: `plans/2026-07-27-integration-throughput.md`

| Zadanie | Stan | Wynik / następny krok |
| --- | --- | --- |
| 1. Transport Pimcore z prywatną sesją | Ukończono | `PimcoreClient` używa prywatnej `requests.Session` przez cały lifecycle klienta i zamyka ją jako context manager. Jawny legacy `opener` nadal korzysta z adaptera `urllib`; oba transporty mają zgodne nagłówki, query, timeout i redakcję API key. Zweryfikowano: 42 passed; kompilacja i `git diff --check`. |
| 2–7 | Nie ruszono | Następne jest zadanie 2: własność klienta, `close` i bezpieczne retry GET. |

## Pakiet 7 — Podział dużych modułów

Plan: `plans/2026-07-27-module-boundaries.md`

| Zadanie | Stan | Wynik / następny krok |
| --- | --- | --- |
| 1–7 | Nie ruszono | Wymaga zakończenia pakietów 3–5. |

## Weryfikacja bazowa

- Domyślne `python` nie inicjalizuje środowiska (brak modułu `encodings`), więc
  testy są uruchamiane przez `.venv\\Scripts\\python.exe`.
- Systemowy katalog tymczasowy pytesta zwracał `PermissionError`; testy używają
  izolowanego `--basetemp` w `.pytest-tmp`.
- Pełny baseline pytest zakończył się: **1193 passed, 20 warnings, 66 subtests
  passed** w 164,22 s. Ostrzeżenia dotyczą istniejącego użycia przestarzałych
  FastAPI `on_event`; nie blokują bieżącego pakietu.
