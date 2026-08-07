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
| 5.6 | SQL zdjęć | W toku | Web używa pojedynczego parametryzowanego UPDATE dla rozpoznanego szablonu; desktopowy `app.py` pozostaje na bezpiecznym fallbacku pojedynczych UPDATE. |
| 5.7 | Benchmark integracyjny i pełna regresja | W toku | Przed commitem wymagane są czyste testy pełnej gałęzi. Lokalny `local_settings.json` wskazuje niedostępny dysk `G:`; pełne testy należy uruchamiać w odłączonym worktree bez tego pliku. |
| 7 | Podział dużych modułów | Nie rozpoczęto | Cel kolejnej połowy pracy, po zamknięciu pakietu 5. |

## Środowisko testowe

- Python: `tmp_pyenv\Scripts\python.exe` (lokalna `.venv` nie jest prawidłowym środowiskiem Windows).
- Node.js LTS jest dostępny w `C:\Program Files\nodejs`.
- Ostrzeżenia FastAPI `on_event` są istniejące i nie blokują pakietu.
