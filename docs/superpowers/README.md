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
| 1–8 | Nie ruszono | Zostanie rozpoczęty po pakiecie 3. |

## Pakiet 5 — Integracje SQL, Pimcore i tłumaczenia

Plan: `plans/2026-07-27-integration-throughput.md`

| Zadanie | Stan | Wynik / następny krok |
| --- | --- | --- |
| 1–7 | Nie ruszono | Zostanie rozpoczęty po pakiecie 4. |

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
