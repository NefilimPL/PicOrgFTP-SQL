# Lokalne wymiary z obrazów w szablonach — plan implementacji

> Dla wykonawców: wymagane jest wykonanie zadań po kolei w cyklu TDD.

Cel: Dodać do szablonów Pimcore lokalne źródła szerokości, głębokości i wysokości odczytywane z obrazów wybranych slotów, z domyślnym progiem pewności OCR 80%.

Architektura: Moduł image_dimensions ukryje PaddleOCR i analizę geometrii za małym interfejsem, więc testy nie będą pobierały modeli. Konfiguracja źródła będzie częścią pojedynczego mapowania Pimcore. Warstwa web_data włączy odczytane wartości do istniejącego katalogu źródeł szablonów, a HTTP zamieni podpisane tokeny slotów na lokalne ścieżki.

Stos technologiczny: Python 3.11, FastAPI, Pillow, opcjonalnie PaddleOCR, PaddlePaddle, OpenCV, JavaScript bez frameworka, pytest.

Specyfikacja: docs/superpowers/specs/2026-08-18-local-image-dimension-template-design.md

## Ograniczenia globalne

- Nie używać płatnego ani zewnętrznego API; obraz pozostaje na hoście aplikacji.
- OCR i modele nie trafiają do requirements-web.txt. Brak opcjonalnych zależności zwraca ocr_unavailable.
- Wspierane rodzaje: width, depth, height.
- minimum_text_confidence jest od 0 do 1 i domyślnie wynosi 0.8; UI pokazuje procent 0–100.
- Istniejące mapowania bez image_dimension działają bez zmiany.
- Renderer ani HTTP nie przyjmuje ścieżki od klienta: używa tylko zweryfikowanego _path_from_file_token.
- Testy jednostkowe nie uruchamiają OCR; wstrzykują fałszywy silnik.

## Struktura plików

- Create: picorgftp_sql/services/image_dimensions.py — modele danych, parser liczby, OCR, geometria, cache i błędy.
- Create: tests/test_image_dimensions.py — testy parsera, progów, etykiet i cache.
- Create: requirements-vision.txt — opcjonalne zależności lokalnego OCR.
- Modify: picorgftp_sql/pimcore_config.py — konfiguracja źródła i walidacja.
- Modify: picorgftp_sql/web_data.py — dostawca wartości przy renderowaniu.
- Modify: picorgftp_sql/web/app.py — bezpieczne rozwiązywanie tokenów slotów.
- Modify: picorgftp_sql/web/static/index.html i picorgftp_sql/web/static/app.js — konfiguracja kreatora i tokeny bieżących slotów.
- Modify: tests/test_pimcore_config.py, tests/test_pimcore_templates.py, tests/test_pimcore_web.py, tests/test_web_ui_integrity.py.
- Modify: docs/pimcore.md — instalacja i instrukcja.

### Task 1: Lokalny, testowalny silnik rozpoznawania

Files:
- Create: picorgftp_sql/services/image_dimensions.py
- Create: tests/test_image_dimensions.py
- Create: requirements-vision.txt

Interfaces:
- ImageDimensionRequest(slot: str, dimension: Literal["width", "depth", "height"], minimum_text_confidence: float).
- OcrTextBox(text: str, confidence: float, bbox: tuple[int, int, int, int], hint: str | None).
- resolve_image_dimensions(requests, slot_paths, recognizer=None) -> tuple[dict[str, str], list[dict[str, str]]].
- image_dimension_source_key(slot, dimension) -> str.

- [ ] Step 1: Write failing parser, threshold and cache tests.

~~~python
class FakeRecognizer:
    def __init__(self):
        self.calls = 0
    def detect(self, _path):
        self.calls += 1
        return [OcrTextBox("130,5 cm", 0.92, (0, 0, 80, 20), "width")]

def test_returns_normalized_value_above_threshold():
    values, warnings = resolve_image_dimensions(
        [ImageDimensionRequest("15", "width", 0.8)],
        {"15": "fixture.png"}, recognizer=FakeRecognizer(),
    )
    assert values == {"IMAGE_DIMENSION:15:WIDTH": "130.5"}
    assert warnings == []

def test_rejects_text_below_mapping_threshold():
    class LowConfidenceRecognizer(FakeRecognizer):
        def detect(self, _path):
            return [OcrTextBox("130,5", 0.74, (0, 0, 80, 20), "width")]
    values, warnings = resolve_image_dimensions(
        [ImageDimensionRequest("15", "width", 0.8)],
        {"15": "fixture.png"}, recognizer=LowConfidenceRecognizer(),
    )
    assert values == {"IMAGE_DIMENSION:15:WIDTH": ""}
    assert warnings[0]["code"] == "image_dimension_low_confidence"
~~~

Add missing-slot, nonnumeric, height-label and two-dimensions-from-one-slot tests; the last must assert FakeRecognizer.calls == 1.

- [ ] Step 2: Run the new tests.

Run: pytest tests/test_image_dimensions.py -v
Expected: FAIL because module image_dimensions does not exist.

- [ ] Step 3: Implement contract, parser and cache.

Create immutable dataclasses. Define:

~~~python
def image_dimension_source_key(slot: str, dimension: str) -> str:
    return f"IMAGE_DIMENSION:{slot}:{dimension.upper()}"
~~~

Normalize decimal commas with Decimal, strip cm/mm/m with no conversion and reject nonpositive numbers. Group requests by slot and call recognizer.detect(path) once per slot. Return empty values for rejected sources. Emit only image_dimension_missing_slot, ocr_unavailable, image_dimension_not_found and image_dimension_low_confidence. Production-only imports live inside PaddleImageDimensionRecognizer; convert ImportError to ImageDimensionUnavailable.

- [ ] Step 4: Implement the PaddleOCR and geometry route.

Use PaddleOCR text bounding boxes/confidence and OpenCV Canny plus HoughLinesP. Prefer labels W/WIDTH/SZER, D/DEPTH/GŁĘB, H/HEIGHT/WYS. Without labels use angles: <=15 degrees width, 75–105 height, 20–70 or 110–160 depth. Return no candidate when association is ambiguous.

Write this content to requirements-vision.txt:

~~~text
paddleocr>=3.0
paddlepaddle>=3.0
opencv-python-headless>=4.10
numpy>=1.26
~~~

- [ ] Step 5: Run focused verification.

Run: pytest tests/test_image_dimensions.py -v
Expected: PASS with no optional OCR dependency installed.

Run: python -c "from picorgftp_sql.services.image_dimensions import image_dimension_source_key; assert image_dimension_source_key('15', 'width') == 'IMAGE_DIMENSION:15:WIDTH'"
Expected: exit code 0.

- [ ] Step 6: Commit.

~~~bash
git add picorgftp_sql/services/image_dimensions.py tests/test_image_dimensions.py requirements-vision.txt
git commit -m "feat: add local image dimension recognizer"
~~~

### Task 2: Konfiguracja mapowania i źródło szablonu

Files:
- Modify: picorgftp_sql/pimcore_config.py
- Modify: tests/test_pimcore_config.py
- Modify: tests/test_pimcore_templates.py

Interfaces:
- Consumes image_dimension_source_key.
- Produces mapping image_dimension: {"slot": "15", "dimension": "width", "minimum_text_confidence": 0.8} or None.
- Produces dynamic SourceDefinition for IMAGE_DIMENSION:15:WIDTH.

- [ ] Step 1: Write failing normalization and validation tests.

~~~python
def test_normalizes_default_image_dimension_confidence():
    settings = normalize_pimcore_settings({"field_mappings": [{
        "source": "WIDTH", "pimcore_field": "width", "type": "input",
        "value_template": "{IMAGE_DIMENSION:15:WIDTH|keep}",
        "image_dimension": {"slot": 15, "dimension": "width"},
    }]})
    assert settings["field_mappings"][0]["image_dimension"] == {
        "slot": "15", "dimension": "width", "minimum_text_confidence": 0.8,
    }

def test_rejects_unconfigured_image_source():
    issues = field_mapping_issues([{
        "source": "WIDTH", "pimcore_field": "width", "type": "input",
        "value_template": "{IMAGE_DIMENSION:15:WIDTH|keep}",
    }])
    assert any("IMAGE_DIMENSION:15:WIDTH" in issue for issue in issues)
~~~

- [ ] Step 2: Run tests.

Run: pytest tests/test_pimcore_config.py tests/test_pimcore_templates.py -v
Expected: FAIL because mapping normalization drops image_dimension and catalog treats it as unknown.

- [ ] Step 3: Implement backward-compatible configuration.

Add _normalize_image_dimension(raw). It accepts positive string/numeric slots, case-folds the three allowed dimensions and defaults omitted confidence to 0.8. Malformed supplied raw values must create a validation error rather than selecting a slot. Add image_dimension in normalize_field_mapping and infer_field_mapping.

In field_mapping_issues create one dynamic source definition per valid config alongside SQL. Test that the existing renderer accepts the configured source through extra_sources and returns extra_values["IMAGE_DIMENSION:15:WIDTH"].

- [ ] Step 4: Run regression tests.

Run: pytest tests/test_pimcore_config.py tests/test_pimcore_templates.py -v
Expected: PASS including all existing SQL and legacy cases.

- [ ] Step 5: Commit.

~~~bash
git add picorgftp_sql/pimcore_config.py tests/test_pimcore_config.py tests/test_pimcore_templates.py
git commit -m "feat: configure image dimension template sources"
~~~

### Task 3: Renderowanie i bezpieczne źródła obrazów

Files:
- Modify: picorgftp_sql/web_data.py
- Modify: picorgftp_sql/web/app.py
- Modify: tests/test_pimcore_web.py

Interfaces:
- Consumes resolve_image_dimensions, image_dimension and slot_tokens.
- Adds keyword-only image_slot_paths: Mapping[str, str] | None = None to preview and runtime render functions.
- Keeps existing response fields values, calculated_values, changed, warnings and integrations.

- [ ] Step 1: Write failing web-data and API tests.

~~~python
def test_preview_renders_configured_image_dimension(monkeypatch):
    monkeypatch.setattr(
        web_data, "resolve_image_dimensions",
        lambda requests, paths: ({"IMAGE_DIMENSION:15:WIDTH": "130.5"}, []),
    )
    result = web_data.preview_pimcore_template(
        {"mappings": [{
            "source": "WIDTH", "pimcore_field": "width", "type": "input",
            "value_template": "{IMAGE_DIMENSION:15:WIDTH|keep}",
            "image_dimension": {"slot": "15", "dimension": "width",
                                "minimum_text_confidence": 0.8},
        }], "target_source": "WIDTH", "product_values": {}, "values": {}},
        image_slot_paths={"15": "dimension.png"},
    )
    assert result["values"]["WIDTH"] == "130.5"
~~~

Add route tests patching _path_from_file_token and assert both template routes receive {"15": "C:/cache/15.png"}, never a raw token.

- [ ] Step 2: Run tests.

Run: pytest tests/test_pimcore_web.py -k "image_dimension or template_preview" -v
Expected: FAIL because render functions neither accept paths nor resolve sources.

- [ ] Step 3: Extend web_data.

Thread image_slot_paths through _render_templates, _render_templates_with_sql_context, preview_pimcore_template and render_saved_pimcore_templates. Before render_mapping_templates, collect unique configs used by selected mappings, call resolve_image_dimensions, append source definitions and extra values, then attach returned warnings to the owning mapping. Preserve SQL order, translation behavior and edit submit preservation.

- [ ] Step 4: Resolve only tokens at HTTP boundary.

Add:

~~~python
def _image_slot_paths_from_payload(payload: object) -> dict[str, str]:
    raw = payload.get("slot_tokens", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Niepoprawna mapa tokenow slotow.")
    return {
        str(slot).strip(): _path_from_file_token(str(token))
        for slot, token in raw.items()
        if str(slot).strip() and str(token).strip()
    }
~~~

After authorization use it in settings preview and runtime rendering. Pass only image_slot_paths to web_data. Preserve current invalid-token 400/403 behavior and never include filesystem paths in JSON.

- [ ] Step 5: Run API regressions.

Run: pytest tests/test_pimcore_web.py tests/test_pimcore_config.py tests/test_pimcore_templates.py -v
Expected: PASS.

- [ ] Step 6: Commit.

~~~bash
git add picorgftp_sql/web_data.py picorgftp_sql/web/app.py tests/test_pimcore_web.py
git commit -m "feat: render dimensions from secured slot images"
~~~

### Task 4: Kreator szablonów i bieżące sloty

Files:
- Modify: picorgftp_sql/web/static/index.html
- Modify: picorgftp_sql/web/static/app.js
- Modify: tests/test_web_ui_integrity.py

Interfaces:
- Consumes image_dimension and slot_tokens.
- Produces pimcoreTemplateImageDimensionValues() and pimcoreSlotTokens().

- [ ] Step 1: Write failing UI integrity tests.

~~~python
def test_template_builder_has_image_dimension_controls(self):
    html = _parse(INDEX_HTML)
    for element_id in (
        "pimcoreTemplateImageDimension", "pimcoreTemplateImageSlot",
        "pimcoreTemplateImageKind", "pimcoreTemplateImageConfidence",
    ):
        self.assertIn(element_id, html.ids)

def test_app_js_sends_image_config_and_slot_tokens(self):
    source = APP_JS.read_text(encoding="utf-8")
    self.assertIn("function pimcoreTemplateImageDimensionValues", source)
    self.assertIn("function pimcoreSlotTokens", source)
    self.assertIn("slot_tokens: pimcoreSlotTokens()", source)
~~~

- [ ] Step 2: Run UI tests.

Run: pytest tests/test_web_ui_integrity.py -k "image_dimension or template_builder" -v
Expected: FAIL because controls and helpers do not exist.

- [ ] Step 3: Add accessible controls and source insertion.

In pimcoreTemplateModal add pimcoreTemplateImageDimension containing enable checkbox, pimcoreTemplateImageSlot, pimcoreTemplateImageKind, pimcoreTemplateImageConfidence. The confidence input is numeric min 0 max 100 step 1 default 80. Populate slots from state.slots, never hard-code 15–17. When enabled add a source button which inserts {IMAGE_DIMENSION:<slot>:<DIMENSION>|keep}. Reject missing slot or an out-of-range confidence before preview/save with modal status text.

- [ ] Step 4: Persist all mapping modes.

Use row.dataset.imageDimension as JSON. Initialize and collect it in pimcoreMappingRow, pimcoreSetupFieldRow and the simple mapping path. In openPimcoreTemplateBuilder prefill controls; in savePimcoreTemplateBuilder save the normalized object. Include it in collectPimcoreMappings, collectPimcoreSetupMappings and collectSimplePimcoreMappings.

- [ ] Step 5: Send signed slots for preview and runtime calculation.

pimcoreSlotTokens() uses state.files.get(prefix).token first, otherwise selectedPhotoToken(state.loadedPhotos.get(prefix), prefix). It excludes deleted, failed and pending-upload slots. Add slot_tokens: pimcoreSlotTokens() to pimcoreTemplatePreviewPayload() and renderPimcoreRuntimeTemplates(). Render image_dimension_* and ocr_unavailable warnings in the current status field. Do not overwrite a manually edited runtime value with an empty recognition result.

- [ ] Step 6: Run client contract tests.

Run: pytest tests/test_web_ui_integrity.py -k "pimcore or image_dimension" -v
Expected: PASS.

- [ ] Step 7: Commit.

~~~bash
git add picorgftp_sql/web/static/index.html picorgftp_sql/web/static/app.js tests/test_web_ui_integrity.py
git commit -m "feat: configure image dimensions in template builder"
~~~

### Task 5: Dokumentacja i pełna weryfikacja

Files:
- Modify: docs/pimcore.md
- Modify: tests/test_pimcore_web.py
- Modify: tests/test_web_ui_integrity.py

- [ ] Step 1: Add an end-to-end token test.

Patch _path_from_file_token so signed-15 becomes C:/cache/15.png. Patch render_saved_pimcore_templates to capture image_slot_paths. POST to /api/pimcore/render-templates with slot_tokens {"15": "signed-15"} and assert a 200 response plus captured path {"15": "C:/cache/15.png"}.

- [ ] Step 2: Run the end-to-end test.

Run: pytest tests/test_pimcore_web.py -k "slot_token" -v
Expected: PASS after Task 3; resolve any contract mismatch before release.

- [ ] Step 3: Document installation and usage.

Add Wymiary z obrazów section to docs/pimcore.md. Include:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt
~~~

Explain the picker workflow, {IMAGE_DIMENSION:15:WIDTH|keep}, default 80%, comma normalization, four diagnostics, local-only privacy and that missing optional dependencies affects only image-derived fields.

- [ ] Step 4: Run full verification.

Run: pytest tests/test_image_dimensions.py tests/test_pimcore_config.py tests/test_pimcore_templates.py tests/test_pimcore_web.py tests/test_web_ui_integrity.py -v
Expected: PASS.

Run: pytest -q
Expected: PASS.

- [ ] Step 5: Commit.

~~~bash
git add docs/pimcore.md tests/test_pimcore_web.py tests/test_web_ui_integrity.py
git commit -m "docs: explain local image dimension templates"
git status --short
~~~

Expected final state: no uncommitted changes.

## Self-review

- Spec coverage: Tasks 1–5 cover local OCR, geometry, confidence, cache, configurable source, secure token path, UI, documentation and regression tests.
- Placeholder scan: Every task identifies files, interfaces, test behavior, commands and expected results.
- Type consistency: ImageDimensionRequest, image_dimension_source_key, resolve_image_dimensions, image_dimension, slot_tokens and image_slot_paths have one spelling across this plan.

