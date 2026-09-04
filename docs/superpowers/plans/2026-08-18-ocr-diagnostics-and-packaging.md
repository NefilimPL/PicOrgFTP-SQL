# Diagnostyka OCR i warianty EXE — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać testowalny ekran diagnostyki lokalnego OCR z nakładką kandydatów oraz dwa warianty budowania web EXE z silnikiem OCR.

**Architecture:** `image_dimensions` rozszerza swój mały interfejs o raport diagnostyczny, który jest wstrzykiwalny w testach i nie zależy od pobranego modelu. Endpoint FastAPI bezpiecznie zamienia token uploadu na lokalny plik, a JavaScript rysuje skalowaną nakładkę nad obrazem i prezentuje wybrane wymiary obok. Skrypt PowerShell instaluję opcjonalne zależności i przekazuje PyInstallerowi komplet danych tylko po użyciu przełączników OCR.

**Tech Stack:** Python 3.11, FastAPI, Pillow, opcjonalnie PaddleOCR/PaddlePaddle/OpenCV, PyInstaller, JavaScript bez frameworka, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-ocr-diagnostics-and-packaging-design.md`

## Global Constraints

- Nie używać płatnego ani zewnętrznego API do analizy obrazu.
- Żadna ścieżka klienta nie może trafić do endpointu; API przyjmuje wyłącznie token podpisanego pliku.
- Domyślny próg to 80% (0.8 w API); akceptowane są wartości od 0 do 1.
- OCR jest opcjonalny: brak zależności zwraca stan `unavailable`, a nie błąd 500.
- `-IncludeVisionModels` działa wyłącznie razem z `-IncludeVision`.
- Testy nie uruchamiają PaddleOCR ani nie pobierają modeli.

---

## Struktura plików

- Modify: `picorgftp_sql/services/image_dimensions.py` — raport diagnostyczny i metadane silnika/modelu.
- Modify: `picorgftp_sql/web/app.py` — bezpieczny endpoint statusu i analizy OCR.
- Modify: `picorgftp_sql/web/static/index.html` — karta ustawień OCR.
- Modify: `picorgftp_sql/web/static/app.js` — upload, analiza i rysowanie nakładki.
- Modify: `picorgftp_sql/web/static/app.css` — układ testera i etykiet prostokątów.
- Modify: `Generator exe/build_common.ps1`, `Generator exe/build_web_exe.ps1`, `Generator exe/BUILD_WEB_EXE.bat` — warianty EXE.
- Modify: `tests/test_image_dimensions.py`, `tests/test_pimcore_web.py`, `tests/test_web_ui_integrity.py`, `tests/test_build_exe_workflow.py`.
- Modify: `docs/pimcore.md` — użycie zakładki i wariantów builda.

### Task 1: Raport diagnostyczny OCR

**Files:**
- Modify: `tests/test_image_dimensions.py`
- Modify: `picorgftp_sql/services/image_dimensions.py`

**Interfaces:**
- Produces `OcrDiagnosticCandidate(text, confidence, bbox, dimension, value, accepted)`.
- Produces `analyze_image_dimensions(path, minimum_text_confidence=0.8, recognizer=None) -> ImageOcrDiagnostics`.
- Produces `image_ocr_runtime_info() -> dict[str, object]` with engine, version, models and GitHub URL.

- [ ] **Step 1: Write failing diagnostics tests.**

```python
def test_diagnostics_classifies_boxes_and_applies_threshold():
    class FakeRecognizer:
        def detect(self, _path):
            return [
                OcrTextBox("130,5 cm", 0.91, (4, 8, 80, 28), "width"),
                OcrTextBox("40", 0.72, (90, 8, 120, 28), "depth"),
            ]

    result = analyze_image_dimensions("fixture.png", 0.8, recognizer=FakeRecognizer())

    assert result.dimensions == {"width": "130.5", "depth": "", "height": ""}
    assert result.candidates[0].accepted is True
    assert result.candidates[1].accepted is False
    assert result.candidates[0].bbox == (4, 8, 80, 28)
```

- [ ] **Step 2: Run test to verify it fails.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_image_dimensions.py -k diagnostics -v`

Expected: FAIL because the diagnostics API does not exist.

- [ ] **Step 3: Implement the smallest report API.**

Build candidates from the recognizer output using existing number parsing and hint normalization. Mark a candidate accepted only when it has a supported dimension, numeric positive value and confidence at least the requested threshold. Choose the highest-confidence accepted candidate per dimension. Convert `ImageDimensionUnavailable` into diagnostics with `available=False` and no candidates.

- [ ] **Step 4: Add runtime metadata test and implementation.**

Test that `image_ocr_runtime_info()` returns `engine.name == "PaddleOCR"`, `github_url` beginning with `https://github.com/`, and `available is False` when optional imports are simulated missing. Implement versions through `importlib.metadata.version`, model names from the recognizer configuration, and stable unavailable fallback without importing PaddleOCR eagerly.

- [ ] **Step 5: Run focused tests.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_image_dimensions.py -v`

Expected: PASS.

### Task 2: Bezpieczne API statusu i analizy

**Files:**
- Modify: `tests/test_pimcore_web.py`
- Modify: `picorgftp_sql/web/app.py`

**Interfaces:**
- `GET /api/ocr/status` returns runtime information after `_require_user`.
- `POST /api/ocr/analyze` accepts `{token: str, minimum_text_confidence: number}` and returns diagnostics plus `image_url`.

- [ ] **Step 1: Write failing route tests.**

```python
def test_ocr_analysis_uses_only_the_signed_upload_token(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(web_app, "_path_from_file_token", lambda token: "C:/cache/test.png")
    monkeypatch.setattr(web_app, "analyze_image_dimensions", lambda path, minimum_text_confidence: captured.update(path=path, threshold=minimum_text_confidence) or FakeDiagnostics())

    response = client.post("/api/ocr/analyze", json={"token": "signed", "minimum_text_confidence": 0.8})

    assert response.status_code == 200
    assert captured == {"path": "C:/cache/test.png", "threshold": 0.8}
    assert "C:/cache" not in response.text
```

Also test malformed threshold returns 400, and `GET /api/ocr/status` returns the service metadata.

- [ ] **Step 2: Run routes to verify they fail.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_pimcore_web.py -k ocr -v`

Expected: FAIL because routes do not exist.

- [ ] **Step 3: Implement endpoint boundary.**

Authorize via `_require_user`, require a nonempty string token, resolve it only through `_path_from_file_token`, validate a finite 0–1 threshold with a 0.8 default, call the service in `run_in_threadpool`, serialize diagnostics explicitly, and return `_versioned_file_url(path, "/api/file", token)` rather than any filesystem path.

- [ ] **Step 4: Run route tests.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_pimcore_web.py -k ocr -v`

Expected: PASS.

### Task 3: Karta Ustawienia → OCR i wizualizacja

**Files:**
- Modify: `tests/test_web_ui_integrity.py`
- Modify: `picorgftp_sql/web/static/index.html`
- Modify: `picorgftp_sql/web/static/app.js`
- Modify: `picorgftp_sql/web/static/app.css`

**Interfaces:**
- `renderSettingsOcr()` renders the tester.
- `renderOcrDiagnostics(result)` renders image overlay and result fields.
- `uploadCachedFile(file, prefix)` is reused without exposing raw paths.

- [ ] **Step 1: Write failing UI contract tests.**

```python
def test_settings_has_ocr_tab_and_tester_controls(self):
    html = _parse(INDEX_HTML)
    self.assertIn("ocr", _settings_tabs(html))
    source = APP_JS.read_text(encoding="utf-8")
    self.assertIn("function renderSettingsOcr()", source)
    self.assertIn("function renderOcrDiagnostics", source)
    self.assertIn("/api/ocr/analyze", source)
```

Add assertions that the renderer uses `data-ocr-overlay`, shows `%`, calls `/api/ocr/status`, and includes the GitHub link supplied by the API.

- [ ] **Step 2: Run test to verify it fails.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_web_ui_integrity.py -k ocr -v`

Expected: FAIL because the OCR tab and renderer are absent.

- [ ] **Step 3: Implement accessible tester UI.**

Add the `ocr` settings-tab button. `renderSettingsOcr()` loads status, renders engine/model/version/link, a file input limited to images, a 0–100 numeric threshold defaulted to 80, a primary Analyze button and an empty results region. Upload with existing cache code and then call the analyze endpoint using only the returned token.

- [ ] **Step 4: Implement scaled overlay and results.**

Render the returned image URL inside a positioned container. On image load, use the image’s natural dimensions to translate each candidate bbox to CSS percentages; create one `data-ocr-overlay` rectangle and a percentage label above it. Use accepted/rejected modifier classes. Render width, depth and height fields from `result.dimensions`, then the unclassified candidate list with raw text, normalized value and confidence.

- [ ] **Step 5: Add styles and verify syntax/contracts.**

Run: `node --check picorgftp_sql/web/static/app.js`

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_web_ui_integrity.py -k ocr -v`

Expected: both PASS.

### Task 4: Warianty pakowania OCR do EXE

**Files:**
- Modify: `tests/test_build_exe_workflow.py`
- Modify: `Generator exe/build_common.ps1`
- Modify: `Generator exe/build_web_exe.ps1`
- Modify: `Generator exe/BUILD_WEB_EXE.bat`

**Interfaces:**
- `Install-BuildDependencies(..., [switch]$IncludeVisionDependencies)` installs `requirements-vision.txt` only when selected.
- `build_web_exe.ps1 -IncludeVision [-IncludeVisionModels]` supplies hidden imports/collection arguments and model cache data.

- [ ] **Step 1: Write failing build behaviour tests.**

Exercise exported PowerShell helper behaviour with a harmless fake `Invoke-Native` command or existing test harness: without `-IncludeVision`, `requirements-vision.txt` is not an install argument; with it, it is. Assert that `-IncludeVisionModels` without `-IncludeVision` exits with a meaningful error and that the vision command includes PaddleOCR/Paddle/OpenCV collection arguments.

- [ ] **Step 2: Run build tests to verify they fail.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_build_exe_workflow.py -k vision -v`

Expected: FAIL because vision switches do not exist.

- [ ] **Step 3: Implement opt-in dependency and PyInstaller options.**

Thread switches from batch to `build_web_exe.ps1` and `Install-BuildDependencies`. With vision, install `requirements-vision.txt` and append `--collect-all paddleocr`, `--collect-all paddle`, `--collect-all cv2` plus necessary hidden imports. Reject models switch unless engine switch is selected.

- [ ] **Step 4: Implement model-cache collection.**

After optional model warmup in the build virtual environment, locate the known Paddle model cache under the current user cache path, validate it is a directory, and copy it under the distributable data directory only for `-IncludeVisionModels`. Do not delete cache content. Emit an actionable message when no models have been downloaded yet.

- [ ] **Step 5: Run build test suite.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_build_exe_workflow.py -v`

Expected: PASS.

### Task 5: Dokumentacja, regresje i build checks

**Files:**
- Modify: `docs/pimcore.md`
- Modify: `tests/test_image_dimensions.py`
- Modify: `tests/test_pimcore_web.py`
- Modify: `tests/test_web_ui_integrity.py`

- [ ] **Step 1: Document usage.**

Document the local-only tester, 80% threshold, meaning of overlays, engine/model/link information, and exact commands:

```powershell
.\Generator exe\build_web_exe.ps1 -IncludeVision
.\Generator exe\build_web_exe.ps1 -IncludeVision -IncludeVisionModels
```

- [ ] **Step 2: Run focused regression set.**

Run: `\.venv-build\Scripts\python.exe -m pytest tests/test_image_dimensions.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py tests/test_build_exe_workflow.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests and client syntax check.**

Run: `\.venv-build\Scripts\python.exe -m pytest -q`

Run: `node --check picorgftp_sql/web/static/app.js`

Expected: PASS. If the pre-existing unavailable `G:\` desktop-fixture failure recurs, record it separately while retaining focused suite evidence.

- [ ] **Step 4: Commit deliberately.**

```powershell
git add docs picorgftp_sql "Generator exe" tests requirements-vision.txt
git commit -m "feat: add OCR diagnostics and EXE options"
git status --short
```

## Self-review

- Spec coverage: Tasks 1–3 implement local tester, safe tokens, boxes, confidence, output fields and metadata; Task 4 implements both EXE variants; Task 5 documents and verifies all paths.
- Placeholder scan: each task defines files, contract, test command and expected effect.
- Type consistency: diagnostic serialization, `minimum_text_confidence`, `image_url`, `IncludeVision` and `IncludeVisionModels` use one name throughout.
