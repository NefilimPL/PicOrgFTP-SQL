(function () {
  const defaults = window.PICORG_EXTENSION_DEFAULTS || {};
  const state = {
    images: [],
    selected: new Set(),
    filters: {
      minWidth: 0,
      minHeight: 0,
      hideThumbnails: false,
      urlFilter: "",
    },
  };

  const panelUrlInput = document.querySelector("#panelUrl");
  const apiTokenInput = document.querySelector("#apiToken");
  const settingsToggle = document.querySelector("#settingsToggle");
  const filtersToggle = document.querySelector("#filtersToggle");
  const settingsPanel = document.querySelector("#settingsPanel");
  const filtersPanel = document.querySelector("#filtersPanel");
  const minWidthInput = document.querySelector("#minWidth");
  const minHeightInput = document.querySelector("#minHeight");
  const hideThumbnailsInput = document.querySelector("#hideThumbnails");
  const urlFilterInput = document.querySelector("#urlFilter");
  const saveSettingsButton = document.querySelector("#saveSettings");
  const testConnectionButton = document.querySelector("#testConnection");
  const scanPageButton = document.querySelector("#scanPage");
  const selectAllButton = document.querySelector("#selectAll");
  const clearSelectionButton = document.querySelector("#clearSelection");
  const uploadSelectedButton = document.querySelector("#uploadSelected");
  const statusOutput = document.querySelector("#status");
  const summaryOutput = document.querySelector("#summary");
  const imagesOutput = document.querySelector("#images");

  function setStatus(text) {
    statusOutput.textContent = text || "";
  }

  function extensionStorageGet(keys) {
    return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
  }

  function extensionStorageSet(values) {
    return new Promise((resolve) => chrome.storage.local.set(values, resolve));
  }

  function normalizePanelUrl(value) {
    return String(value || "").trim().replace(/\/+$/, "");
  }

  function imageFilename(url, fallback = "web-image.jpg") {
    try {
      const path = new URL(url).pathname;
      const name = decodeURIComponent(path.split("/").pop() || "").trim();
      return name || fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function imageMimeType(url, fallback = "image/jpeg") {
    const lower = String(url || "").toLowerCase().split("?", 1)[0];
    if (lower.endsWith(".png")) return "image/png";
    if (lower.endsWith(".webp")) return "image/webp";
    if (lower.endsWith(".gif")) return "image/gif";
    if (lower.endsWith(".bmp")) return "image/bmp";
    if (lower.endsWith(".avif")) return "image/avif";
    return fallback;
  }

  function positiveInt(value) {
    const parsed = parseInt(String(value || "0"), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }

  function readFilters() {
    state.filters = {
      minWidth: positiveInt(minWidthInput?.value),
      minHeight: positiveInt(minHeightInput?.value),
      hideThumbnails: Boolean(hideThumbnailsInput?.checked),
      urlFilter: String(urlFilterInput?.value || "").trim().toLowerCase(),
    };
    return state.filters;
  }

  async function saveFilters() {
    readFilters();
    await extensionStorageSet({ filters: state.filters });
  }

  function applyFiltersToInputs() {
    if (minWidthInput) minWidthInput.value = String(state.filters.minWidth || 0);
    if (minHeightInput) minHeightInput.value = String(state.filters.minHeight || 0);
    if (hideThumbnailsInput) hideThumbnailsInput.checked = Boolean(state.filters.hideThumbnails);
    if (urlFilterInput) urlFilterInput.value = state.filters.urlFilter || "";
  }

  function isThumbnailImage(image) {
    const width = Number(image?.width || 0);
    const height = Number(image?.height || 0);
    const text = `${image?.url || ""} ${image?.source || ""} ${image?.kind || ""}`.toLowerCase();
    return (
      image?.kind === "thumbnail" ||
      /thumb|thumbnail|small|mini|cart_default|home_default|small_default/.test(text) ||
      (width > 0 && height > 0 && Math.max(width, height) <= 320)
    );
  }

  function imagePassesFilters(image) {
    const filters = readFilters();
    const width = Number(image?.width || 0);
    const height = Number(image?.height || 0);
    const url = String(image?.url || "").toLowerCase();
    if (filters.urlFilter && !url.includes(filters.urlFilter)) return false;
    if (filters.hideThumbnails && isThumbnailImage(image)) return false;
    if (filters.minWidth && width && width < filters.minWidth) return false;
    if (filters.minHeight && height && height < filters.minHeight) return false;
    return true;
  }

  function visibleImageEntries() {
    return state.images
      .map((image, index) => ({ image, index }))
      .filter((entry) => imagePassesFilters(entry.image));
  }

  function collectImagesFromPage() {
    const imageExtensions = /\.(jpe?g|png|webp|gif|bmp|tiff?|avif)(\?|#|$)/i;
    const ignored = /^(data:|javascript:|mailto:|tel:)/i;
    const seen = new Set();
    const result = [];

    function absoluteUrl(raw) {
      const value = String(raw || "").replace(/&amp;/g, "&").replace(/\\\//g, "/").trim();
      if (!value || ignored.test(value)) return "";
      try {
        return new URL(value, document.baseURI).href.split("#", 1)[0];
      } catch (_error) {
        return "";
      }
    }

    function kindFrom(url, source, width, height) {
      const text = `${url} ${source}`.toLowerCase();
      if (/thumb|thumbnail|small|mini|cart_default|home_default|small_default/.test(text)) {
        return "thumbnail";
      }
      if (width && height && Math.max(width, height) <= 320) {
        return "thumbnail";
      }
      return "image";
    }

    function add(raw, source, width = 0, height = 0) {
      const url = absoluteUrl(raw);
      if (!url || !imageExtensions.test(url) || seen.has(url)) return;
      seen.add(url);
      result.push({
        url,
        filename: url.split("/").pop() || "web-image.jpg",
        width: Number(width || 0),
        height: Number(height || 0),
        size_bytes: 0,
        mime_type: "",
        source,
        kind: kindFrom(url, source, Number(width || 0), Number(height || 0)),
      });
    }

    function parseSrcset(value, source, fallbackWidth = 0, fallbackHeight = 0) {
      String(value || "")
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean)
        .forEach((part) => {
          const bits = part.split(/\s+/);
          let width = fallbackWidth;
          for (const bit of bits.slice(1)) {
            if (/^\d+(\.\d+)?w$/i.test(bit)) {
              width = parseInt(bit, 10) || fallbackWidth;
              break;
            }
          }
          add(bits[0], source, width, fallbackHeight);
        });
    }

    document.querySelectorAll("img, source, a, link, meta").forEach((node) => {
      const width = parseInt(node.getAttribute("width") || node.naturalWidth || "0", 10) || 0;
      const height = parseInt(node.getAttribute("height") || node.naturalHeight || "0", 10) || 0;
      for (const attr of [
        "src",
        "href",
        "content",
        "data-src",
        "data-original",
        "data-lazy",
        "data-lazy-src",
        "data-full",
        "data-full-src",
        "data-image",
        "data-image-src",
        "data-image-large-src",
        "data-large",
        "data-large-src",
        "data-zoom-image",
        "data-zoom-src",
        "poster",
      ]) {
        add(node.getAttribute(attr), `${node.tagName.toLowerCase()}.${attr}`, width, height);
      }
      for (const attr of ["srcset", "data-srcset", "data-lazy-srcset"]) {
        parseSrcset(node.getAttribute(attr), `${node.tagName.toLowerCase()}.${attr}`, width, height);
      }
    });

    document.querySelectorAll("[style]").forEach((node) => {
      const style = node.getAttribute("style") || "";
      for (const match of style.matchAll(/url\(\s*['"]?([^'")]+)['"]?\s*\)/gi)) {
        add(match[1], "style.background");
      }
    });

    const html = document.documentElement.innerHTML.replace(/\\\//g, "/");
    for (const match of html.matchAll(/(?:https?:)?\/\/[^"'<>\s\\)]+?\.(?:jpe?g|png|webp|gif|bmp|tiff?|avif)(?:\?[^"'<>\s\\)]*)?/gi)) {
      add(match[0], "html.url");
    }
    for (const match of html.matchAll(/["'](\/[^"'<>\s\\]+?\.(?:jpe?g|png|webp|gif|bmp|tiff?|avif)(?:\?[^"'<>\s\\]*)?)["']/gi)) {
      add(match[1], "html.relative-url");
    }

    return {
      pageUrl: location.href,
      title: document.title,
      images: result.slice(0, 240),
    };
  }

  async function currentTab() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tabs.length || !tabs[0].id) {
      throw new Error("Nie znaleziono aktywnej karty.");
    }
    return tabs[0];
  }

  async function scanPage() {
    setStatus("Skanowanie");
    const tab = await currentTab();
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: collectImagesFromPage,
    });
    const payload = results && results[0] ? results[0].result : { images: [] };
    state.images = payload.images || [];
    state.selected = new Set(state.images.map((_image, index) => index));
    await extensionStorageSet({ lastPageUrl: payload.pageUrl || tab.url || "" });
    renderImages();
    setStatus("Gotowe");
  }

  function renderImages() {
    imagesOutput.textContent = "";
    const visible = visibleImageEntries();
    const selectedVisible = visible.filter((entry) => state.selected.has(entry.index)).length;
    summaryOutput.textContent = state.images.length
      ? `${selectedVisible}/${visible.length} widocznych zaznaczonych, ${state.images.length} wykrytych.`
      : "Brak zeskanowanych zdjec.";
    visible.forEach(({ image, index }) => {
      const row = document.createElement("label");
      const checkbox = document.createElement("input");
      const preview = document.createElement("img");
      const meta = document.createElement("div");
      const title = document.createElement("strong");
      const dimensions = document.createElement("small");
      const url = document.createElement("span");
      row.className = "image-row";
      checkbox.type = "checkbox";
      checkbox.checked = state.selected.has(index);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          state.selected.add(index);
        } else {
          state.selected.delete(index);
        }
        renderImages();
      });
      preview.src = image.url;
      preview.alt = "";
      title.textContent = image.filename || imageFilename(image.url);
      dimensions.textContent =
        image.width && image.height ? `${image.width} x ${image.height}` : "rozmiar nieznany";
      url.textContent = image.url;
      meta.append(title, dimensions, url);
      row.append(checkbox, preview, meta);
      imagesOutput.appendChild(row);
    });
  }

  async function saveSettings() {
    const settings = {
      panelUrl: normalizePanelUrl(panelUrlInput.value),
      apiToken: apiTokenInput.value.trim(),
    };
    await extensionStorageSet(settings);
    setStatus("Zapisano");
  }

  async function loadSettings() {
    const stored = await extensionStorageGet(["panelUrl", "apiToken", "lastPageUrl", "filters"]);
    const panelUrl = normalizePanelUrl(stored.panelUrl || defaults.panelUrl || "http://127.0.0.1:8010");
    const apiToken = stored.apiToken || defaults.apiToken || "";
    panelUrlInput.value = panelUrl;
    apiTokenInput.value = apiToken;
    if (stored.filters && typeof stored.filters === "object") {
      state.filters = {
        ...state.filters,
        ...stored.filters,
        minWidth: positiveInt(stored.filters.minWidth),
        minHeight: positiveInt(stored.filters.minHeight),
        hideThumbnails: Boolean(stored.filters.hideThumbnails),
        urlFilter: String(stored.filters.urlFilter || ""),
      };
    }
    applyFiltersToInputs();
    if (!stored.panelUrl || (!stored.apiToken && apiToken)) {
      await extensionStorageSet({ panelUrl, apiToken });
    }
  }

  async function testConnection() {
    await saveSettings();
    const panelUrl = normalizePanelUrl(panelUrlInput.value);
    const apiToken = apiTokenInput.value.trim();
    setStatus("Test");
    const response = await fetch(`${panelUrl}/api/browser-extension/ping`, {
      headers: { Authorization: `Bearer ${apiToken}` },
    });
    if (!response.ok) {
      throw new Error(`Panel odrzucil polaczenie: ${response.status}`);
    }
    setStatus("Polaczono");
  }

  async function uploadImage(image, pageUrl) {
    const imageResponse = await fetch(image.url, {
      credentials: "include",
      cache: "no-cache",
    });
    if (!imageResponse.ok) {
      throw new Error(`Nie udalo sie pobrac obrazu ${imageResponse.status}: ${image.url}`);
    }
    const blob = await imageResponse.blob();
    const filename = imageFilename(image.url);
    const file = new File([blob], filename, { type: blob.type || imageMimeType(image.url) });
    const form = new FormData();
    form.append("file", file, filename);
    form.append("prefix", "web");
    form.append("source_url", image.url);
    form.append("page_url", pageUrl || "");

    const panelUrl = normalizePanelUrl(panelUrlInput.value);
    const apiToken = apiTokenInput.value.trim();
    const uploadResponse = await fetch(`${panelUrl}/api/browser-extension/upload-cache`, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiToken}` },
      body: form,
    });
    const payload = await uploadResponse.json().catch(() => ({}));
    if (!uploadResponse.ok) {
      throw new Error(payload.detail || `Panel odrzucil upload: ${uploadResponse.status}`);
    }
    return payload;
  }

  async function uploadSelected() {
    await saveSettings();
    const stored = await extensionStorageGet(["lastPageUrl"]);
    const selected = visibleImageEntries()
      .filter((entry) => state.selected.has(entry.index))
      .map((entry) => entry.image);
    if (!selected.length) {
      setStatus("Brak wyboru");
      return;
    }
    uploadSelectedButton.disabled = true;
    let uploaded = 0;
    try {
      for (const image of selected) {
        setStatus(`${uploaded + 1}/${selected.length}`);
        await uploadImage(image, stored.lastPageUrl || "");
        uploaded += 1;
      }
      setStatus(`Wyslano ${uploaded}`);
      summaryOutput.textContent = "W panelu kliknij Odbierz z rozszerzenia.";
    } finally {
      uploadSelectedButton.disabled = false;
    }
  }

  saveSettingsButton.addEventListener("click", () => {
    saveSettings().catch((error) => setStatus(error.message));
  });
  settingsToggle.addEventListener("click", () => {
    settingsPanel.hidden = !settingsPanel.hidden;
  });
  filtersToggle.addEventListener("click", () => {
    filtersPanel.hidden = !filtersPanel.hidden;
  });
  for (const input of [minWidthInput, minHeightInput, hideThumbnailsInput, urlFilterInput]) {
    input.addEventListener("input", () => {
      saveFilters().catch((error) => setStatus(error.message));
      renderImages();
    });
    input.addEventListener("change", () => {
      saveFilters().catch((error) => setStatus(error.message));
      renderImages();
    });
  }
  testConnectionButton.addEventListener("click", () => {
    testConnection().catch((error) => setStatus(error.message));
  });
  scanPageButton.addEventListener("click", () => {
    scanPage().catch((error) => setStatus(error.message));
  });
  selectAllButton.addEventListener("click", () => {
    for (const entry of visibleImageEntries()) {
      state.selected.add(entry.index);
    }
    renderImages();
  });
  clearSelectionButton.addEventListener("click", () => {
    state.selected.clear();
    renderImages();
  });
  uploadSelectedButton.addEventListener("click", () => {
    uploadSelected().catch((error) => setStatus(error.message));
  });

  loadSettings()
    .then(() => scanPage())
    .catch((error) => setStatus(error.message));
})();
