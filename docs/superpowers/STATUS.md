# Rejestr postępu

Stan: 2026-08-07. Ten plik jest jedynym bieżącym rejestrem wykonania; plany i specyfikacje pozostają dokumentami historycznymi.

| Pakiet | Zakres | Stan | Potwierdzenie / ograniczenie |
| --- | --- | --- | --- |
| 1 | SQLite lifecycle i telemetria | Ukończono | Historycznie zweryfikowano. |
| 2 | Wyszukiwanie produktów i start desktopu | Ukończono | Historycznie zweryfikowano. |
| 3 | Upload, obrazy i kolejka | Ukończono | Historycznie zweryfikowano. |
| 4 | FTP i indeks plików | Ukończono | 8 z 8 zadań; poprzednia pełna regresja: 1247 testów i 66 subtestów. |
| 5.1 | Poller runtime | Zweryfikowano | `node --test tests/js/runtime-status.test.js`: 7/7; benchmark pytest: 5/5. Pierwotny timeout CI nie odtwarza się lokalnie, więc nie wprowadzono nieuzasadnionej zmiany cyklu życia. |
| 5.2 | Lifecycle Pimcore | Ukończono | Scope domyka klienty własne, w tym pracę asynchroniczną; klient przekazany przez wywołującego nie jest zamykany. |
| 5.3 | SQL w renderze | Ukończono | Jeden kontekst renderu współdzieli połączenie per profil i zawsze je domyka. |
| 5.4 | Tłumaczenia | Ukończono | TTL/LRU, singleflight i unieważnienie cache po zaakceptowanej zmianie ustawień; ostrzeżenia nie są cache’owane. |
| 5.5 | Niezależne tłumaczenia | Ukończono | Maksymalnie 4 workery, zachowana kolejność; SQL nie jest współużywany równolegle. |
| 5.6 | SQL zdjęć | Ukończono | Web i desktop używają pojedynczego parametryzowanego UPDATE dla rozpoznanego standardowego szablonu; niestandardowe szablony zachowują fallback pojedynczych UPDATE. Zweryfikowano testami batch/SQL sync. |
| 5.7 | Benchmark integracyjny i pełna regresja | Ukończono | Deterministyczny benchmark potwierdza 1 klienta Pimcore, 2 połączenia SQL, 4 unikalne tłumaczenia, 1 statement zdjęć i maks. 4 workery. W czystym worktree: 1267 testów pytest przeszło; po ustawieniu `C:\Program Files\nodejs` benchmark pytest przeszedł 5/5, a testy Node 7/7. |
| 7.1 | Charakterystyka tras i granic importów | Ukończono | `tests/test_module_boundaries.py`: snapshot tras i guard importów serwisów przechodzą. |
| 7.2 | Router procesów | Ukończono | `process_api.py` zawiera upload/staging, listę, aktywne zadania, szczegóły i anulowanie z jawnymi zależnościami. Snapshot tras i skonfigurowany `Retry-After` dla limitu kolejki zachowane. |
| 7.3 | Router runtime, indeksu i obecności | Ukończono | `runtime_api.py` obsługuje runtime status, status/odświeżenie indeksu oraz obecność. Rejestracja zachowuje kolejność tras; testy skoncentrowane: 20 przeszło. |
| 7.4 | Kontroler podglądu FTP w desktopie | Ukończono | `desktop_ftp_preview.py` zachowuje kontrakt EAN, odrzuca spóźnione wyniki i używa kolejki odbieranej wyłącznie przez UI. Zweryfikowano 45 testami oraz dwoma rundami niezależnego przeglądu. |
| 7.5 | Moduł autouzupełniania | Ukończono | `autocomplete.js` udostępnia kontroler i adapter DOM przez `window.PicOrg`; zachowano debounce, obsługę aktualnego żądania i UI. |
| 7.6 | Moduł kolejki procesów | Ukończono | `process-jobs.js` współdzieli trwające odświeżenie i reaguje na wersję kolejki runtime bez osobnego pollera; moduł usuwa wcześniejsze 404 assetu. |
| 7.7 | Assety, shimy, benchmark i pełna regresja | W toku | Następny krok: kompletna weryfikacja, pakowanie assetów i końcowe porządki. |

## Środowisko testowe

- Python: `tmp_pyenv\Scripts\python.exe` (lokalna `.venv` nie jest prawidłowym środowiskiem Windows).
- Node.js LTS jest dostępny w `C:\Program Files\nodejs`.
- Ostrzeżenia FastAPI `on_event` są istniejące i nie blokują pakietu.
