# FTP and File Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ograniczyć pełne listingi FTP i lokalne skany, przechowywać indeks tylko raz oraz bezpiecznie sprzątać tymczasowe podglądy.

**Architecture:** `RemoteListingCache` utrzymuje procesowy snapshot nazw z TTL 60 s, capability targeted `NLST` i singleflight pełnego odświeżenia. Lokalny `LocalFileIndex` ładuje świeżą generację segmentów i nie skanuje przy każdym starcie; zmienione segmenty są zapisywane atomowo jako nowa generacja. `FtpTempManager` jest jedynym właścicielem katalogów podglądu i usuwa wyłącznie kanoniczne dzieci zarządzanego root.

**Tech Stack:** Python 3.14, `ftplib`, SQLite, filesystem Windows/network shares, `threading.Condition`, pytest.

## Global Constraints

- FTP zachowuje jeden płaski katalog; nie twórz, nie przenoś i nie używaj subfolderów per EAN.
- Brak obsługi wildcard nie oznacza braku zdjęć i zawsze ma bezpieczny fallback.
- Domyślny TTL listingu FTP wynosi 60 s; domyślny TTL lokalnego indeksu wynosi 15 min.
- Upload i delete aktualizują lub unieważniają cache natychmiast po potwierdzonym wyniku.
- Stary kompletny indeks pozostaje aktywny po błędzie refreshu.
- SQLite przechowuje jedną logiczną kopię indeksu, nie pełny blob plus równoważne segmenty.
- Cleanup usuwa tylko katalogi z dokładnym prefiksem aplikacji, kanonicznie znajdujące się pod temp root.
- Nie zmieniaj nazw plików, parsera slotów, konfiguracji FTP ani ręcznego pełnego refreshu.

## File Structure

- Create: `picorgftp_sql/services/ftp_listing_cache.py`
- Create: `picorgftp_sql/services/ftp_temp_manager.py`
- Create: `picorgftp_sql/file_index_segments.py`
- Create: `tests/test_ftp_listing_cache.py`
- Create: `tests/test_ftp_temp_manager.py`
- Create: `tests/test_file_index_performance.py`
- Modify: `picorgftp_sql/services/ftp_service.py:29-128`
- Modify: `picorgftp_sql/file_index.py:81-430`
- Modify: `picorgftp_sql/sqlite_store.py:752-1120,3968-4055`
- Modify: `picorgftp_sql/data_store.py:288-299`
- Modify: `picorgftp_sql/web_data.py:380-405,3555-3578`
- Modify: `picorgftp_sql/app.py:454-478,971-988,6087-6300`
- Delete after call-site audit: `picorgftp_sql/services/file_index_service.py`
- Delete after call-site audit: `picorgftp_sql/services/directory_index_service.py`
- Modify: `tests/test_ftp_service.py`
- Modify: `tests/test_file_index.py`
- Modify: `tests/test_sqlite_store.py`

---

### Task 1: Procesowy cache listingu z singleflight

**Files:**

- Create: `picorgftp_sql/services/ftp_listing_cache.py`
- Create: `tests/test_ftp_listing_cache.py`

**Interfaces:**

- Produces: `RemoteFileRecord`; `RemoteListingCache.get_or_refresh(config, loader, now=None)`; `apply_uploaded`, `apply_deleted`, `invalidate`.
- Consumes: callable `loader() -> list[RemoteFileRecord]`.

- [ ] **Step 1: Napisz test TTL**

```python
FTP_CONFIG = {
    "host": "ftp.example.test",
    "port": 21,
    "user": "operator",
    "pass": "test-secret",
    "path": "/photos",
    "pasv": True,
}


def test_listing_cache_reuses_snapshot_within_ttl():
    cache = RemoteListingCache(ttl_seconds=60)
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return [RemoteFileRecord(name="5901_01.jpg")]

    first = cache.get_or_refresh(FTP_CONFIG, loader, now=100.0)
    second = cache.get_or_refresh(FTP_CONFIG, loader, now=159.9)

    assert first == second
    assert calls == 1
```

`FTP_CONFIG` w teście zawiera host, port, user, pass, path i pasv; test musi również sprawdzić, że `repr(cache)` oraz klucz diagnostyczny nie zawierają hasła.

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_ftp_listing_cache.py::test_listing_cache_reuses_snapshot_within_ttl -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Zaimplementuj bezpieczny klucz lokalizacji**

Utwórz losowy, procesowy klucz HMAC i licz fingerprint z host/port/user/password/path/pasv. W mapie przechowuj tylko digest. Nigdy nie zwracaj materiału wejściowego w `repr` ani logach.

```python
def _location_key(config: Mapping[str, object]) -> str:
    material = json.dumps(
        [
            str(config.get("host") or ""),
            int(config.get("port") or 21),
            str(config.get("user") or ""),
            str(config.get("pass") or ""),
            str(config.get("path") or ""),
            bool(config.get("pasv", True)),
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(_PROCESS_CACHE_SECRET, material, hashlib.sha256).hexdigest()
```

- [ ] **Step 4: Dodaj singleflight test**

Zablokuj loader eventem, uruchom 12 równoległych `get_or_refresh`, zwolnij event i oczekuj jednego wywołania loadera oraz identycznych wyników.

- [ ] **Step 5: Zaimplementuj singleflight**

Dla każdego klucza utrzymuj `Condition`, `refreshing` i ostatni kompletny snapshot. Pierwszy caller wykonuje loader bez globalnej blokady. Pozostali czekają. Błąd loadera budzi wszystkich i nie zastępuje starego snapshotu pustą listą.

- [ ] **Step 6: Dodaj przyrostową invalidację**

`apply_uploaded(config, records)` podmienia rekord o tej samej nazwie lub dodaje nowy. `apply_deleted(config, names)` usuwa dokładne nazwy. `invalidate(config)` oznacza snapshot jako expired.

- [ ] **Step 7: Uruchom testy cache**

Run: `python -m pytest tests/test_ftp_listing_cache.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/services/ftp_listing_cache.py tests/test_ftp_listing_cache.py
git commit -m "perf: cache remote ftp listings"
```

### Task 2: Selektywne `NLST` z capability i fallbackiem

**Files:**

- Modify: `picorgftp_sql/services/ftp_service.py:29-80`
- Modify: `picorgftp_sql/services/ftp_listing_cache.py`
- Modify: `tests/test_ftp_service.py`
- Modify: `tests/test_ftp_listing_cache.py`

**Interfaces:**

- Produces: `list_remote_records_for_ean(ftp_conn, ean, capability) -> TargetedListingResult`.
- Consumes: płaski katalog i istniejącą konwencję nazwy zaczynającej się od EAN.

- [ ] **Step 1: Napisz test pozytywnego wildcard bez pełnego `MLSD`**

```python
class FakeFTP:
    def __init__(self):
        self.nlst_results = {}
        self.nlst_calls = []
        self.mlsd_calls = 0

    def nlst(self, pattern=None):
        self.nlst_calls.append(pattern)
        return list(self.nlst_results.get(pattern, []))

    def mlsd(self):
        self.mlsd_calls += 1
        return iter(())


def test_targeted_nlst_returns_ean_files_without_full_listing():
    ftp = FakeFTP()
    ftp.nlst_results["5901_*"] = ["5901_01.jpg", "5901_02.png"]

    result = list_remote_records_for_ean(ftp, "5901", capability="unknown")

    assert [item.name for item in result.records] == ["5901_01.jpg", "5901_02.png"]
    assert result.capability == "supported"
    assert ftp.mlsd_calls == 0
    assert ftp.nlst_calls == ["5901_*"]
```

- [ ] **Step 2: Napisz test pustej niewiarygodnej odpowiedzi**

Przy `capability="unknown"` i pustym `NLST("5901_*")` test oczekuje `requires_full_listing=True`. Przy `capability="supported"` ten sam pusty wynik oznacza wiarygodne zero rekordów.

- [ ] **Step 3: Napisz test błędu składni**

`ftplib.error_perm("500 wildcard unsupported")` ma zwrócić `capability="unsupported"` i `requires_full_listing=True`, nie pustą listę zdjęć.

- [ ] **Step 4: Uruchom testy i potwierdź brak targeted API**

Run: `python -m pytest tests/test_ftp_service.py -k "targeted or wildcard" -v`

Expected: FAIL podczas importu albo z pełnym listingiem.

- [ ] **Step 5: Zaimplementuj tri-state capability**

Użyj tylko wartości `unknown`, `supported`, `unsupported`. Wzorzec to dokładnie `f"{normalized_ean}_*"`. Wszystkie zwrócone nazwy ponownie przepuść przez `select_remote_files_for_ean`, aby serwer nie mógł poszerzyć wyniku wildcard.

Nie wywołuj `cwd`, `mkd`, `rename` ani innych komend struktury katalogów.

- [ ] **Step 6: Podłącz cache do `list_remote_files_for_ean`**

Strategia:

1. świeży pełny snapshot z cache;
2. targeted `NLST`, jeśli capability nie jest unsupported;
3. pełny `list_remote_filenames`, jeśli wynik targeted wymaga fallbacku;
4. zapis pełnego snapshotu do cache.

Każdy lookup nadal poprawnie zamyka własne połączenie FTP.

- [ ] **Step 7: Uruchom testy FTP**

Run: `python -m pytest tests/test_ftp_service.py tests/test_ftp_listing_cache.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/services/ftp_service.py picorgftp_sql/services/ftp_listing_cache.py tests/test_ftp_service.py tests/test_ftp_listing_cache.py
git commit -m "perf: use safe targeted ftp listing"
```

### Task 3: Invalidacja cache po synchronizacji FTP

**Files:**

- Modify: `picorgftp_sql/services/ftp_service.py:131-260`
- Modify: `tests/test_ftp_service.py`
- Modify: `tests/test_ftp_listing_cache.py`

**Interfaces:**

- Consumes: wynik potwierdzonego `STOR`/`DELE`.
- Produces: cache odzwierciedlający każdy potwierdzony sukces; invalidacja po niepewnym wyniku.

- [ ] **Step 1: Napisz test uploadu widocznego bez nowego listingu**

Wykonaj pierwszy lookup z pełnym cache, zamockuj udany `STOR 5901_03.jpg`, następnie lookup w TTL. Oczekuj nowej nazwy i braku drugiego `MLSD/NLST`.

- [ ] **Step 2: Napisz test częściowego błędu**

Pierwszy upload sukces, drugi wyjątek po rozpoczęciu synchronizacji. Oczekuj oznaczenia snapshotu expired, aby następny lookup wykonał pełne odświeżenie.

- [ ] **Step 3: Uruchom testy i potwierdź nieaktualny cache**

Run: `python -m pytest tests/test_ftp_service.py -k "cache_after or partial_sync" -v`

Expected: FAIL, ponieważ sync nie aktualizuje cache.

- [ ] **Step 4: Aktualizuj cache dopiero po potwierdzonej komendzie**

Po każdym udanym `storbinary` wywołaj `apply_uploaded`. Po udanym `delete` wywołaj `apply_deleted`. W szerokim handlerze częściowego błędu wywołaj `invalidate` przed zwróceniem obecnego wyniku błędu.

- [ ] **Step 5: Uruchom regresję synchronizacji**

Run: `python -m pytest tests/test_ftp_service.py tests/test_web_app_files.py -k "ftp" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/services/ftp_service.py tests/test_ftp_service.py tests/test_ftp_listing_cache.py
git commit -m "fix: invalidate ftp listing cache after sync"
```

### Task 4: Start lokalnego indeksu bez automatycznego pełnego skanu

**Files:**

- Modify: `picorgftp_sql/file_index.py:81-340`
- Modify: `picorgftp_sql/web_data.py:380-405`
- Modify: `picorgftp_sql/app.py:287-294,971-988`
- Modify: `tests/test_file_index.py`

**Interfaces:**

- Produces: `LocalFileIndex.cache_is_fresh(now=None) -> bool`; `refresh_if_stale(force=False) -> bool`.
- Consumes: `generated_at`, root, wersję indeksu i TTL 900 s.

- [ ] **Step 1: Napisz test świeżego cache bez startu workera**

```python
def make_index_with_cache(tmp_path, generated_at_epoch):
    root = tmp_path / "photos"
    root.mkdir()
    cache_path = tmp_path / "file-index.json"
    generated_at = datetime.fromtimestamp(
        generated_at_epoch,
        timezone.utc,
    ).isoformat().replace("+00:00", "Z")
    cache_path.write_text(
        json.dumps({
            "version": INDEX_VERSION,
            "root": str(root.resolve()),
            "generated_at": generated_at,
            "dirs_scanned": 0,
            "products_scanned": 0,
            "names": [],
            "types": {},
            "models": {},
            "colors": {},
            "extras": {},
            "files": {},
        }),
        encoding="utf-8",
    )
    return LocalFileIndex(str(root), str(cache_path))


def test_refresh_if_stale_skips_fresh_cached_snapshot(tmp_path, monkeypatch):
    index = make_index_with_cache(tmp_path, generated_at_epoch=1_000.0)
    assert index.load_cache()
    started = []
    monkeypatch.setattr(index, "refresh_async", lambda: started.append(True))

    assert index.refresh_if_stale(now=1_899.0) is False
    assert started == []
```

- [ ] **Step 2: Dodaj test starego i manualnego refreshu**

Przy `now=1900.1` oczekuj startu. `force=True` zawsze startuje, niezależnie od wieku.

- [ ] **Step 3: Uruchom test i potwierdź brak metody**

Run: `python -m pytest tests/test_file_index.py -k "refresh_if_stale" -v`

Expected: FAIL z `AttributeError`.

- [ ] **Step 4: Zaimplementuj parser czasu i politykę**

`cache_is_fresh` wymaga zgodnego `INDEX_VERSION`, tego samego kanonicznego root i poprawnego `generated_at`. Niepoprawny timestamp oznacza stale. `refresh_if_stale` wywołuje `refresh_async` tylko przy braku/nieświeżym snapshotcie lub force.

- [ ] **Step 5: Przełącz desktop i web**

Po `load_cache()` wywołuj `refresh_if_stale`, nie bezwarunkowe `refresh_async`. Endpoint/manualny przycisk przekazuje `force=True`.

- [ ] **Step 6: Uruchom testy indeksu/startu**

Run: `python -m pytest tests/test_file_index.py tests/test_app_performance_helpers.py tests/test_web_app_files.py -k "file_index or index" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/file_index.py picorgftp_sql/web_data.py picorgftp_sql/app.py tests/test_file_index.py tests/test_app_performance_helpers.py tests/test_web_app_files.py
git commit -m "perf: skip fresh file index refresh at startup"
```

### Task 5: Jedna segmentowa reprezentacja SQLite

**Files:**

- Create: `picorgftp_sql/file_index_segments.py`
- Modify: `picorgftp_sql/sqlite_store.py:752-1120,3968-4055`
- Modify: `picorgftp_sql/data_store.py:288-299`
- Modify: `picorgftp_sql/file_index.py:122-158,272-294`
- Modify: `tests/test_sqlite_store.py:832-861`
- Modify: `tests/test_file_index.py:57-145`

**Interfaces:**

- Produces: `FileIndexGeneration`; `load_file_index_generation(key="default")`; `commit_file_index_generation(generation, segments)`.
- Consumes: stary `file_index_cache.payload_json` wyłącznie podczas migracji.

- [ ] **Step 1: Napisz test atomowej migracji bloba**

Zapisz legacy payload tylko do `file_index_cache`, uruchom inicjalizację/migrację, a następnie sprawdź:

```python
generation = store.load_file_index_generation()
assert generation.complete is True
assert generation.snapshot["names"] == ["ALFA"]
with store.connection() as conn:
    legacy = conn.execute(
        "SELECT payload_json FROM file_index_cache WHERE cache_key = 'default'"
    ).fetchone()
    segment_count = conn.execute(
        "SELECT COUNT(*) FROM file_index_segments"
    ).fetchone()[0]
assert legacy is None or legacy[0] in ("", "{}")
assert segment_count > 0
```

- [ ] **Step 2: Uruchom test i potwierdź podwójną reprezentację**

Run: `python -m pytest tests/test_sqlite_store.py -k "file_index_generation or legacy_file_index" -v`

Expected: FAIL, ponieważ API generacji nie istnieje.

- [ ] **Step 3: Dodaj schemat generacji**

Dodaj tabelę metadanych z `cache_key`, `generation_id`, `root`, `version`, `generated_at`, `complete` oraz rozszerz klucz segmentów o `generation_id`. Użyj nowej wersji schematu zgodnie z aktualnym mechanizmem migracji.

Nie kasuj legacy bloba przed zapisaniem wszystkich segmentów i ustawieniem `complete=1` w tej samej transakcji.

- [ ] **Step 4: Dodaj konwersję snapshot ↔ segmenty**

W `file_index_segments.py` umieść dataclass oraz czyste funkcje:

```python
@dataclass(frozen=True)
class FileIndexSegment:
    segment_key: str
    section: str
    lookup_key: str
    payload: object


def normalize_segment_key(value: object) -> str:
    text = str(value or "").strip().upper()
    for character in text:
        if character.isalnum():
            return character if character.isascii() else "_"
    return "_"


def snapshot_to_segments(snapshot: dict[str, object]) -> list[FileIndexSegment]:
    rows: list[FileIndexSegment] = []
    for name in snapshot.get("names", []):
        rows.append(FileIndexSegment(
            segment_key=normalize_segment_key(name),
            section="names",
            lookup_key=str(name).upper(),
            payload=name,
        ))
    for section in ("types", "models", "colors", "extras", "files"):
        values = snapshot.get(section, {})
        if not isinstance(values, dict):
            continue
        for lookup_key, payload in sorted(values.items()):
            name_key = str(lookup_key).split("\x1f", 1)[0]
            rows.append(FileIndexSegment(
                segment_key=normalize_segment_key(name_key),
                section=section,
                lookup_key=str(lookup_key),
                payload=payload,
            ))
    return rows


def segments_to_snapshot(
    generation: FileIndexGeneration,
    segments: Iterable[FileIndexSegment],
) -> dict[str, object]:
    snapshot = generation.empty_snapshot()
    for segment in segments:
        if segment.section == "names":
            snapshot["names"].append(segment.payload)
        else:
            snapshot[segment.section][segment.lookup_key] = segment.payload
    snapshot["names"].sort()
    return snapshot
```

`FileIndexGeneration.empty_snapshot()` zwraca metadane generacji i puste
sekcje `names`, `types`, `models`, `colors`, `extras`, `files`.

- [ ] **Step 5: Zapisuj przez `executemany`**

Nowa generacja powstaje jako incomplete, segmenty są zapisywane jednym `executemany`, następnie generacja staje się complete i poprzednia jest usuwana w jednej transakcji. `save_file_index_cache` przestaje zapisywać pełny payload.

- [ ] **Step 6: Przełącz `LocalFileIndex.load_cache`**

Cache store zwraca zrekonstruowany snapshot aktywnej kompletnej generacji. Błąd lub incomplete generation zwraca poprzednią complete, nie pusty indeks.

- [ ] **Step 7: Uruchom testy migracji i indeksu**

Run: `python -m pytest tests/test_sqlite_store.py tests/test_file_index.py -k "file_index" -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/file_index_segments.py picorgftp_sql/sqlite_store.py picorgftp_sql/data_store.py picorgftp_sql/file_index.py tests/test_sqlite_store.py tests/test_file_index.py
git commit -m "perf: store file index as atomic segments"
```

### Task 6: Przyrostowe odświeżanie segmentów

**Files:**

- Modify: `picorgftp_sql/file_index_segments.py`
- Modify: `picorgftp_sql/file_index.py:158-270`
- Modify: `picorgftp_sql/sqlite_store.py:3968-4055`
- Modify: `tests/test_file_index.py`
- Create: `tests/test_file_index_performance.py`

**Interfaces:**

- Produces: `DirectoryFingerprint`; `scan_changed_segments(root, previous) -> SegmentRefresh`.
- Consumes: mtime katalogu, liczba bezpośrednich wpisów i `INDEX_VERSION`.

- [ ] **Step 1: Napisz test jednego zmienionego produktu**

Utwórz dwa kompletne katalogi produktów, zbuduj indeks, następnie dodaj plik tylko do drugiego. Zamockuj `_file_names` spy i oczekuj ponownego parsowania drugiego segmentu bez odczytu plików pierwszego.

- [ ] **Step 2: Napisz test niepewnego mtime**

Wstrzyknij provider fingerprintów zwracający `reliable=False`. Oczekuj `full_scan_required=True`, nie reuse starego segmentu.

- [ ] **Step 3: Uruchom test i potwierdź pełny skan**

Run: `python -m pytest tests/test_file_index.py -k "changed_segment or unreliable_fingerprint" -v`

Expected: FAIL, oba produkty są skanowane.

- [ ] **Step 4: Dodaj stabilny fingerprint**

```python
@dataclass(frozen=True)
class DirectoryFingerprint:
    canonical_path: str
    mtime_ns: int
    entry_count: int
    parser_version: int
    reliable: bool = True
```

Fingerprint nie zawiera treści plików. Zmieniony mtime/count lub wersja parsera wymusza skan segmentu.

- [ ] **Step 5: Zbuduj nową generację z reuse**

Nowa generacja kopiuje niezmienione segmenty jednym parametrycznym
zapytaniem typu `INSERT-SELECT` zbudowanym tak:

```python
key_markers = ", ".join("?" for _key in reused_segment_keys)
query = (
    "INSERT INTO file_index_segments "
    "(generation_id, segment_key, section, lookup_key, payload_json, updated_at) "
    "SELECT ?, segment_key, section, lookup_key, payload_json, ? "
    "FROM file_index_segments "
    f"WHERE generation_id = ? AND segment_key IN ({key_markers})"
)
params = (
    new_generation_id,
    generated_at,
    previous_generation_id,
    *reused_segment_keys,
)
```

Nie dekoduj przy tym JSON w Pythonie. Zmienione segmenty są zastępowane, a
usunięte nie przechodzą do nowej generacji.

- [ ] **Step 6: Uruchom testy atomowości**

Wstrzyknij wyjątek w połowie zapisu zmienionych segmentów. Oczekuj poprzedniej complete generation i braku częściowo aktywnej nowej.

- [ ] **Step 7: Uruchom pakiet indeksu**

Run: `python -m pytest tests/test_file_index.py tests/test_file_index_performance.py tests/test_sqlite_store.py -k "file_index" -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/file_index_segments.py picorgftp_sql/file_index.py picorgftp_sql/sqlite_store.py tests/test_file_index.py tests/test_file_index_performance.py
git commit -m "perf: refresh file index incrementally"
```

### Task 7: Zarządzany lifecycle temp FTP

**Files:**

- Create: `picorgftp_sql/services/ftp_temp_manager.py`
- Create: `tests/test_ftp_temp_manager.py`
- Modify: `picorgftp_sql/services/ftp_service.py:82-128`
- Modify: `picorgftp_sql/app.py:454-478,6087-6300`
- Modify: `tests/test_ftp_service.py`

**Interfaces:**

- Produces: `FtpTempManager.create_request_dir`, `release`, `cleanup_stale`, `close`.
- Consumes: systemowy temp root, request ID i cancel event.

- [ ] **Step 1: Napisz test odmowy usunięcia poza root**

```python
def test_release_refuses_path_outside_temp_root(tmp_path):
    manager = FtpTempManager(str(tmp_path / "managed"))
    outside = tmp_path / "outside"
    outside.mkdir()
    assert manager.release(str(outside)) is False
    assert outside.exists()
```

- [ ] **Step 2: Napisz test TTL i aktywnego katalogu**

Utwórz dwa poprawnie nazwane katalogi starsze niż 24 h, oznacz jeden jako aktywny. `cleanup_stale` usuwa wyłącznie nieaktywny. Katalog o podobnym, ale nieidentycznym prefiksie pozostaje.

- [ ] **Step 3: Uruchom test i potwierdź brak managera**

Run: `python -m pytest tests/test_ftp_temp_manager.py -v`

Expected: FAIL podczas importu.

- [ ] **Step 4: Zaimplementuj kanonizację i rejestr aktywnych**

Każda ścieżka przechodzi `Path.resolve()`. Warunek usunięcia wymaga `candidate.parent == managed_root` oraz nazwy zaczynającej się od `picorgftp_sql_ftp_`. Użyj natywnego `shutil.rmtree` tylko po tych sprawdzeniach.

- [ ] **Step 5: Podłącz desktop i anulowanie**

Każdy lookup tworzy katalog przez manager. Zmiana request ID ustawia cancel event; `download_remote_slots` sprawdza event między plikami. Stary katalog zwalniany jest po zakończeniu/wyjątku. `App.destroy` wywołuje `manager.close()`.

- [ ] **Step 6: Uruchom testy FTP/temp**

Run: `python -m pytest tests/test_ftp_temp_manager.py tests/test_ftp_service.py tests/test_app_performance_helpers.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/services/ftp_temp_manager.py picorgftp_sql/services/ftp_service.py picorgftp_sql/app.py tests/test_ftp_temp_manager.py tests/test_ftp_service.py tests/test_app_performance_helpers.py
git commit -m "fix: clean managed ftp preview files"
```

### Task 8: Usuń nieaktywne indeksy i wykonaj benchmark

**Files:**

- Delete: `picorgftp_sql/services/file_index_service.py`
- Delete: `picorgftp_sql/services/directory_index_service.py`
- Modify: `tests/test_file_index_performance.py`
- Modify: `docs/superpowers/specs/2026-07-27-ftp-and-file-indexing-design.md`

**Interfaces:**

- Consumes: kanoniczny `picorgftp_sql.file_index.LocalFileIndex`.
- Produces: brak duplikatów i raport dla 100 000 FTP names oraz 1% zmian indeksu.

- [ ] **Step 1: Potwierdź brak runtime call sites**

Run: `rg -n "services\\.file_index_service|services\\.directory_index_service|from .*file_index_service|DirectoryIndex" picorgftp_sql tests`

Expected: wyłącznie definicje w dwóch usuwanych plikach; brak importów runtime i dynamicznych nazw w testach/buildzie.

- [ ] **Step 2: Usuń dwa nieaktywne moduły**

Usuń pliki przez mechanizm patchowania repozytorium. Następnie:

Run: `rg -n "file_index_service|directory_index_service|DirectoryIndex" picorgftp_sql tests`

Expected: 0 wyników.

- [ ] **Step 3: Dodaj benchmark listingu**

Wygeneruj 100 000 nazw, w tym pliki dla 100 EAN. Zmierz pierwszy pełny lookup, 100 lookupów w TTL i invalidację po uploadzie. Asercje funkcjonalne: jeden pełny listing w TTL i zero pełnych listingów po przyrostowej aktualizacji.

- [ ] **Step 4: Dodaj benchmark 1% zmian**

W syntetycznym indeksie 10 000 segmentów oznacz 100 jako zmienione. Oczekuj `segments_scanned == 100`, `segments_reused == 9900` oraz jednej aktywnej complete generation.

- [ ] **Step 5: Uruchom pakiet**

Run: `python -m pytest tests/test_ftp_listing_cache.py tests/test_ftp_service.py tests/test_ftp_temp_manager.py tests/test_file_index.py tests/test_file_index_performance.py tests/test_sqlite_store.py -q`

Expected: PASS.

- [ ] **Step 6: Uruchom pełną regresję**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql tests/test_file_index_performance.py docs/superpowers/specs/2026-07-27-ftp-and-file-indexing-design.md
git commit -m "refactor: remove inactive file index implementations"
```

## Final Verification

- [ ] Run: `python -m pytest -q`
- [ ] Run: `python -m compileall -q picorgftp_sql tests`
- [ ] Run: `git diff --check`
- [ ] W logu testowego FTP potwierdź brak `MKD`, `RNFR`, `RNTO` i katalogów per EAN.
- [ ] Potwierdź fallback wildcard, jeden listing w TTL, atomową generację i cleanup temp.
- [ ] Dołącz benchmark pełnego katalogu 100k oraz przyrostowego skanu 1%.
