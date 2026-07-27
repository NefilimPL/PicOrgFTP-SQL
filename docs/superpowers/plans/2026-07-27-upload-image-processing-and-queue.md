# Upload Image Processing and Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Utrzymać event loop responsywny podczas uploadu, kodować każdy raster jednym końcowym pipeline'em i egzekwować ograniczoną wspólną kolejkę procesowania.

**Architecture:** Rezerwacja miejsca następuje przed stagingiem. `UploadStagingService` strumieniuje dane i deleguje walidację, Pillow oraz Defender do ograniczonego executora, ale nie koduje pliku pośrednio. `ImagePipeline` wykonuje końcową transformację i binarne dobieranie jakości. `ProcessQueueService` ma własny `deque`, condition, workerów, limit globalny/per użytkownik i kontrolowane anulowanie.

**Tech Stack:** Python 3.14, FastAPI/Starlette, `threading`, `collections.deque`, Pillow, Microsoft Defender subprocess, pytest.

## Global Constraints

- Walidacja typu, sygnatury, limitu pikseli i Microsoft Defender pozostają obowiązkowe.
- Domyślnie działa 1 worker, maksymalnie 8 oczekujących zadań i 2 zadania per właściciel.
- Pełna kolejka zwraca `429` z `Retry-After` przed pełnym stagingiem.
- Stan końcowy jest trwały, a katalog joba sprzątany po sukcesie, błędzie i anulowaniu.
- Foreground i background używają tej samej kolejki.
- Nie zmieniaj nazw plików, slotów, katalogów produktów, kolejności FTP/SQL ani obecnych limitów użytkownika.
- Surowy staged upload nie może być serwowany przez endpoint preview/download.
- Operacji FTP, SQL ani atomowego zapisu nie przerywaj w połowie.

## File Structure

- Create: `picorgftp_sql/web/process_queue.py` — rezerwacje, kolejka, workerzy i anulowanie.
- Create: `picorgftp_sql/web/upload_staging.py` — strumieniowanie, walidacja i AV.
- Create: `picorgftp_sql/image_pipeline.py` — wspólna transformacja web/desktop.
- Create: `tests/test_process_queue.py`
- Create: `tests/test_upload_staging.py`
- Create: `tests/test_image_pipeline.py`
- Create: `tests/helpers_process_upload.py`
- Create: `tests/test_upload_event_loop_performance.py`
- Modify: `picorgftp_sql/web/app.py:1037-1280,1515-1640,3579-3959,6651-6744`
- Modify: `picorgftp_sql/web_workflow.py:320-560`
- Modify: `picorgftp_sql/app.py:7600-7750`
- Modify: `tests/test_web_app_files.py:343-825,1986-2050`
- Modify: `tests/test_image_utils.py`

---

### Task 1: Bounded `ProcessQueueService`

**Files:**

- Create: `picorgftp_sql/web/process_queue.py`
- Create: `tests/test_process_queue.py`

**Interfaces:**

- Produces: `QueueLimits`, `QueueReservation`, `ProcessQueueFull`, `OwnerQueueLimit`, `ProcessQueueService.reserve`, `submit`, `cancel`, `position`, `shutdown`.
- Consumes: `owner_id`, `job_id` i callable `run(job_id, cancel_event)`.

- [ ] **Step 1: Napisz test globalnego i właścicielskiego limitu**

```python
def test_reservations_enforce_global_and_owner_limits():
    queue = ProcessQueueService(
        QueueLimits(workers=1, max_pending=2, max_per_owner=1),
        start_workers=False,
    )
    first = queue.reserve("owner-a")
    with pytest.raises(OwnerQueueLimit):
        queue.reserve("owner-a")
    second = queue.reserve("owner-b")
    with pytest.raises(ProcessQueueFull) as error:
        queue.reserve("owner-c")
    assert error.value.retry_after_seconds == 2
    first.release()
    second.release()
```

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_process_queue.py::test_reservations_enforce_global_and_owner_limits -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Zaimplementuj rezerwacje**

```python
@dataclass(frozen=True)
class QueueLimits:
    workers: int = 1
    max_pending: int = 8
    max_per_owner: int = 2
    retry_after_seconds: int = 2


class ProcessQueueFull(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        super().__init__("process queue is full")
        self.retry_after_seconds = retry_after_seconds
```

Rezerwacja ma unikalny losowy token, `owner_id`, stan `reserved/submitted/released` i idempotentne `release()`. Wszystkie liczniki są zmieniane pod jednym `Condition`.

- [ ] **Step 4: Napisz test kolejności, pozycji i cancel**

Użyj dwóch bramek `threading.Event`. Pierwszy job blokuje workera, drugi i trzeci czekają. Oczekuj pozycji 1 i 2. Anuluj drugi i sprawdź, że trzeci przechodzi na pozycję 1 oraz drugi runner nie został wywołany.

- [ ] **Step 5: Dodaj worker loop**

Worker pod `Condition` pobiera pierwszy submitted job z `deque`, ustawia `running`, zwalnia blokadę i wywołuje runner. W `finally` ustawia terminalny stan kolejki, zwalnia licznik właściciela i powiadamia oczekujących.

`cancel(job_id)`:

- usuwa submitted job i ustawia jego event;
- dla running tylko ustawia event;
- dla terminalnego zwraca `False`.

- [ ] **Step 6: Uruchom pełne testy kolejki**

Run: `python -m pytest tests/test_process_queue.py -v`

Expected: PASS bez pozostawionych żywych workerów.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/process_queue.py tests/test_process_queue.py
git commit -m "feat: add bounded process queue"
```

### Task 2: Rezerwacja przed stagingiem i bezpieczny upload staging

**Files:**

- Create: `picorgftp_sql/web/upload_staging.py`
- Create: `tests/test_upload_staging.py`
- Modify: `picorgftp_sql/web/app.py:1037-1280,1515-1640`
- Modify: `tests/test_web_app_files.py:343-825`

**Interfaces:**

- Produces: `StagedUpload`; `UploadStagingService.stage(upload, job_dir, prefix) -> StagedUpload`.
- Consumes: `UploadFile`, istniejące ustawienia security i wstrzyknięte blokujące funkcje validate/scan.

- [ ] **Step 1: Napisz test, że blokujące funkcje działają w innym wątku**

```python
from io import BytesIO
from PIL import Image
from starlette.datastructures import UploadFile


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (100, 100), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def upload_file(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


@pytest.mark.anyio
async def test_stage_runs_validation_and_scan_off_event_loop(tmp_path):
    event_loop_thread = threading.get_ident()
    worker_threads = []

    def validate(path, filename, max_pixels):
        worker_threads.append(threading.get_ident())
        return (100, 100)

    def scan(path):
        worker_threads.append(threading.get_ident())
        return {"status": "clean"}

    service = UploadStagingService(validate_image=validate, scan_file=scan)
    result = await service.stage(
        upload_file("photo.jpg", jpeg_bytes()),
        str(tmp_path),
        "01",
    )

    assert result.path.endswith(".jpg")
    assert worker_threads
    assert all(thread_id != event_loop_thread for thread_id in worker_threads)
```

Umieść `jpeg_bytes` i `upload_file` w
`tests/helpers_process_upload.py`, aby kolejne testy route oraz pipeline
używały identycznych danych.

- [ ] **Step 2: Uruchom test i potwierdź brak usługi**

Run: `python -m pytest tests/test_upload_staging.py::test_stage_runs_validation_and_scan_off_event_loop -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Zaimplementuj strumieniowanie i immutable wynik**

```python
@dataclass(frozen=True)
class StagedUpload:
    path: str
    original_name: str
    detected_extension: str
    size_bytes: int
    width: int | None
    height: int | None
```

`stage()` czyta `UploadFile` porcjami po 1 MiB, egzekwuje limit podczas zapisu i usuwa częściowy plik przy każdym wyjątku. `validate_image` oraz `scan_file` uruchamia przez `run_in_threadpool`.

Nie wywołuj `_strip_upload_metadata`. Staged path pozostaje wewnętrzny.

- [ ] **Step 4: Przenieś istniejące walidatory bez zmiany reguł**

Przenieś kod `_validate_upload_image_file`, wykrywania sygnatury i `_scan_uploaded_file` do `upload_staging.py`, zachowując parametry i komunikaty. W `web/app.py` pozostaw importy i cienkie adaptery tylko wtedy, gdy istniejące testy bezpośrednio patchują stare symbole; usuń adapter po przełączeniu testów.

- [ ] **Step 5: Dodaj test zakazu serwowania raw staged file**

Przejdź wszystkie endpointy cache/preview. Test ma wywołać endpoint z tokenem wskazującym staged raw path i oczekiwać odmowy albo wygenerowanej miniatury, nigdy identycznych bajtów źródłowych zawierających EXIF.

- [ ] **Step 6: Uruchom security regression**

Run: `python -m pytest tests/test_upload_staging.py tests/test_web_app_files.py -k "upload or antivirus or pixel or metadata or executable" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/web/upload_staging.py picorgftp_sql/web/app.py tests/test_upload_staging.py tests/test_web_app_files.py
git commit -m "perf: stage uploads outside event loop"
```

### Task 3: Jeden końcowy `ImagePipeline`

**Files:**

- Create: `picorgftp_sql/image_pipeline.py`
- Create: `tests/test_image_pipeline.py`
- Modify: `picorgftp_sql/web_workflow.py:320-560`
- Modify: `picorgftp_sql/app.py:7600-7750`
- Modify: `tests/test_image_utils.py`
- Modify: testy metadata w `tests/test_web_app_files.py`

**Interfaces:**

- Produces: `ImagePipelineOptions`; `ImagePipelineResult`; `process_image(source_path, target_path, options)`.
- Consumes: obecne ustawienia resize/content-fit/format/jakość/max bytes.

- [ ] **Step 1: Napisz test końcowego usunięcia EXIF i pojedynczego open**

```python
def write_jpeg_with_exif(path: Path) -> Path:
    image = Image.new("RGB", (120, 80), "white")
    exif = Image.Exif()
    exif[0x010E] = "private description"
    image.save(path, format="JPEG", exif=exif)
    return path


def test_pipeline_removes_metadata_and_opens_source_once(tmp_path, monkeypatch):
    source = write_jpeg_with_exif(tmp_path / "source.jpg")
    target = tmp_path / "target.jpg"
    opens = 0
    original_open = Image.open

    def counted_open(path, *args, **kwargs):
        nonlocal opens
        if str(path) == str(source):
            opens += 1
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Image, "open", counted_open)
    process_image(str(source), str(target), ImagePipelineOptions(target_format="JPEG"))

    assert opens == 1
    with original_open(target) as result:
        assert not result.getexif()
```

Zaimportuj `Path`, `Image` i helpery pipeline na początku testu.

- [ ] **Step 2: Uruchom test i potwierdź brak modułu**

Run: `python -m pytest tests/test_image_pipeline.py::test_pipeline_removes_metadata_and_opens_source_once -v`

Expected: FAIL podczas importu.

- [ ] **Step 3: Zaimplementuj kolejność transformacji**

W jednej funkcji:

```python
with Image.open(source_path) as opened:
    image = ImageOps.exif_transpose(opened)
    image.load()
    image = normalize_mode(image, options.target_format)
    image = apply_content_fit(image, options)
    image.thumbnail(options.max_dimensions, Image.Resampling.LANCZOS)
    result = save_final_image(image, target_path, options)
return result
```

`save_final_image` zapisuje do pliku tymczasowego w katalogu celu i używa `os.replace` dopiero po sukcesie. Nie przekazuje `exif`, `icc_profile` ani innych metadanych, chyba że istniejąca konfiguracja jawnie wymaga zachowania profilu koloru.

- [ ] **Step 4: Napisz test maksymalnie sześciu kodowań**

Wydziel helper o sygnaturze
`choose_jpeg_quality(minimum, maximum, max_attempts, max_bytes, measure)`,
gdzie `measure(quality) -> int` koduje do zarządzanego pliku tymczasowego i
zwraca liczbę bajtów. Test:

```python
attempted_qualities = []


def measure(quality: int) -> int:
    attempted_qualities.append(quality)
    return 400_000 if quality <= 70 else 700_000


quality = choose_jpeg_quality(
    minimum=10,
    maximum=95,
    max_attempts=6,
    max_bytes=500_000,
    measure=measure,
)
assert len(attempted_qualities) <= 6
assert quality == max(item for item in attempted_qualities if item <= 70)
```

- [ ] **Step 5: Przełącz web i desktop**

`web_workflow._save_image_with_options` i desktopowy odpowiednik delegują do `process_image`. Usuń obie liniowe pętle `quality -= 5` dopiero po przejściu testów kontraktowych dla JPEG, PNG i pozostałych formatów.

Pliki niebędące rastrami zachowują istniejącą ścieżkę passthrough.

- [ ] **Step 6: Uruchom testy obrazów**

Run: `python -m pytest tests/test_image_pipeline.py tests/test_image_utils.py tests/test_web_image_import.py tests/test_web_app_files.py -k "image or metadata or exif or upload_cache" -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add picorgftp_sql/image_pipeline.py picorgftp_sql/web_workflow.py picorgftp_sql/app.py tests/test_image_pipeline.py tests/test_image_utils.py tests/test_web_app_files.py
git commit -m "perf: consolidate final image processing"
```

### Task 4: Wspólna kolejka dla foreground i background

**Files:**

- Modify: `picorgftp_sql/web/app.py:3579-3959,6651-6744`
- Modify: `tests/test_process_queue.py`
- Modify: `tests/test_web_app_files.py:1986-2050`

**Interfaces:**

- Consumes: `ProcessQueueService` i `UploadStagingService`.
- Produces: jedna funkcja `_reserve_and_stage_process(request, form) -> QueuedProcess`; odpowiedź `429` z `Retry-After`.

- [ ] **Step 1: Napisz test, że pełna kolejka odrzuca przed stagingiem**

```python
def test_background_process_rejects_before_materializing_when_queue_is_full(
    client, monkeypatch
):
    staging = Mock()
    full_queue = Mock()
    full_queue.reserve.side_effect = ProcessQueueFull(retry_after_seconds=2)
    monkeypatch.setattr(web_app, "_PROCESS_QUEUE", full_queue)
    monkeypatch.setattr(web_app, "_UPLOAD_STAGING", staging)

    response = client.post(
        "/api/process/background",
        files={
            "file_01": (
                "photo.jpg",
                jpeg_bytes(),
                "image/jpeg",
            )
        },
        data={
            "ean": "5901234567890",
            "name": "ALFA",
            "type_name": "STÓŁ",
            "model": "A1",
        },
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
    staging.stage.assert_not_called()
```

- [ ] **Step 2: Uruchom test i potwierdź obecny staging**

Run: `python -m pytest tests/test_web_app_files.py -k "rejects_before_materializing" -v`

Expected: FAIL, staging jest wykonywany albo endpoint nie zwraca 429.

- [ ] **Step 3: Rezerwuj po `cache_scope`, nie po zmiennym IP**

W obu endpointach wyznacz `owner_id = _user_cache_scope(request, username)`. Wywołaj `reserve(owner_id)` przed `_materialize_process_form`. Przy `ProcessQueueFull`/`OwnerQueueLimit` zwróć 429. Każdy wyjątek stagingu zwalnia rezerwację w `finally`.

- [ ] **Step 4: Przełącz background submit**

Po sukcesie stagingu utwórz job, przypisz reservation i wywołaj `ProcessQueueService.submit`. Usuń bezpośrednie `_PROCESS_EXECUTOR.submit`.

- [ ] **Step 5: Przełącz foreground**

Foreground tworzy ten sam job i submituje do tej samej kolejki. Czeka na terminalny `threading.Event` z timeoutem równym obecnemu kontraktowi requestu. Nie uruchamia `_process_upload_snapshot` przez ogólny Starlette threadpool.

Odpowiedź zachowuje dotychczasowy payload. Background może dodać `queue_position`.

- [ ] **Step 6: Dodaj test współdzielenia limitu**

Zablokuj jedynego workera, wyślij background i foreground tego samego właściciela, a trzecie żądanie oczekuj jako 429. Zwolnij worker i sprawdź oba wyniki.

- [ ] **Step 7: Uruchom testy route/job**

Run: `python -m pytest tests/test_process_queue.py tests/test_web_app_files.py -k "process or queue or job" -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add picorgftp_sql/web/app.py tests/test_process_queue.py tests/test_web_app_files.py
git commit -m "feat: route all processing through bounded queue"
```

### Task 5: Anulowanie i bezpieczny cleanup katalogów jobów

**Files:**

- Modify: `picorgftp_sql/web/process_queue.py`
- Modify: `picorgftp_sql/web/app.py:3579-3959`
- Modify: `picorgftp_sql/web/upload_staging.py`
- Modify: `tests/test_process_queue.py`
- Modify: `tests/test_upload_staging.py`
- Modify: `tests/test_web_app_files.py`

**Interfaces:**

- Produces: endpoint anulowania istniejącego joba lub rozszerzenie aktualnego endpointu; `cleanup_job_directory(path, active_paths) -> bool`.
- Consumes: cancel event z queue runnera.

- [ ] **Step 1: Napisz test bezpieczeństwa ścieżki cleanup**

```python
def test_cleanup_refuses_directory_outside_managed_root(tmp_path):
    managed = tmp_path / "managed"
    managed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    assert cleanup_job_directory(str(outside), managed_root=str(managed)) is False
    assert outside.exists()
```

- [ ] **Step 2: Napisz test każdego stanu końcowego**

Parametryzuj `completed`, `failed`, `cancelled`. Utwórz katalog joba z plikiem, zakończ runner odpowiednim stanem i oczekuj braku katalogu oraz usunięcia wpisu rezerwacji.

- [ ] **Step 3: Dodaj token między etapami**

Przed walidacją kolejnego slotu, finalnym pipeline, FTP i SQL sprawdź `cancel_event.is_set()`. Jeśli ustawiony przed rozpoczęciem zewnętrznej operacji, przejdź do `cancelled`. Po rozpoczęciu atomowego zapisu/FTP/SQL zakończ bieżącą operację, a dopiero potem anuluj następny etap.

- [ ] **Step 4: Dodaj cleanup TTL**

Cleanup wybiera tylko dzieci `managed_root`, których nazwa zaczyna się od dokładnego prefiksu jobów, mtime jest starsze niż 24 godziny i kanoniczna ścieżka nie występuje w `active_paths`.

- [ ] **Step 5: Uruchom testy cleanup/anulowania**

Run: `python -m pytest tests/test_process_queue.py tests/test_upload_staging.py tests/test_web_app_files.py -k "cancel or cleanup or process_job" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add picorgftp_sql/web/process_queue.py picorgftp_sql/web/upload_staging.py picorgftp_sql/web/app.py tests/test_process_queue.py tests/test_upload_staging.py tests/test_web_app_files.py
git commit -m "feat: cancel process jobs and clean staging"
```

### Task 6: Event-loop i pipeline benchmark

**Files:**

- Create: `tests/test_upload_event_loop_performance.py`
- Modify: `tests/test_ci_performance_smoke.py`
- Modify: `docs/superpowers/specs/2026-07-27-upload-image-processing-and-queue-design.md`

**Interfaces:**

- Consumes: ukończony staging, pipeline i queue.
- Produces: benchmark 26 slotów oraz równoległego `/api/health`.

- [ ] **Step 1: Dodaj fixture 26 reprezentatywnych obrazów**

Generuj lokalnie Pillow obrazy o różnych wymiarach i orientacji EXIF. Nie używaj sieci, FTP ani Defendera w benchmarku; wstrzyknij deterministyczny clean scanner z opóźnieniem CPU/I/O odpowiadającym osobnemu workerowi.

- [ ] **Step 2: Mierz health równolegle z procesem**

Uruchom process request w osobnym kliencie, a drugi klient odpytuje `/api/health` co 50 ms do zakończenia joba. Zapisz próbki i oblicz p95.

```python
assert health_p95 < 0.250
assert max(queue_depth_samples) <= 8
assert all(attempts <= 6 for attempts in jpeg_encode_attempts)
```

- [ ] **Step 3: Dodaj pomiar cleanup i pamięci**

Po jobie oczekuj braku aktywnego katalogu. Użyj `tracemalloc` do raportu peak, ale nie ustawiaj kruchego absolutnego limitu RAM w CI; porównuj w opisie PR z baseline na tej samej maszynie.

- [ ] **Step 4: Uruchom testy pakietu**

Run: `python -m pytest tests/test_process_queue.py tests/test_upload_staging.py tests/test_image_pipeline.py tests/test_upload_event_loop_performance.py tests/test_web_app_files.py -q`

Expected: PASS.

- [ ] **Step 5: Uruchom pełną regresję**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_upload_event_loop_performance.py tests/test_ci_performance_smoke.py docs/superpowers/specs/2026-07-27-upload-image-processing-and-queue-design.md
git commit -m "test: cover upload queue responsiveness"
```

## Final Verification

- [ ] Run: `python -m pytest -q`
- [ ] Run: `python -m compileall -q picorgftp_sql tests`
- [ ] Run: `git diff --check`
- [ ] Potwierdź 429 przed stagingiem, wspólną kolejkę foreground/background i cleanup trzech stanów końcowych.
- [ ] Potwierdź brak osłabienia walidacji oraz brak raw staged file w odpowiedziach HTTP.
- [ ] Dołącz p95 health, liczbę kodowań i peak temp/RAM przed oraz po zmianie.
