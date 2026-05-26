const state = {
  slots: [],
  files: new Map(),
  filePreviewUrls: new Map(),
  loadedPhotos: new Map(),
  deletedSlots: new Map(),
  lists: {},
  entries: [],
  selectedList: "names",
  settings: null,
  currentUser: null,
  isAdmin: false,
  fileIndex: null,
  photosLoading: false,
  loadedEntryOriginal: null,
  slotFits: new Map(),
  defaultSlotFit: false,
  slotSources: new Map(),
  draggedSlotPrefix: "",
  lastLookupMs: null,
  activeSettingsTab: "app",
  history: null,
  logs: null,
  settingsSecrets: null,
  theme: localStorage.getItem("picorg-theme") || "light",
  suppressAutoSearch: false,
  lastAutoSearchKey: "",
  photoLoadRequestId: 0,
  photoSourceStatus: new Map(),
  listFilter: "",
  declinedListPrompts: new Set(),
  activeListPromptKeys: new Set(),
  colorFieldLabels: {},
  ftpPreviewLoading: new Set(),
  ftpPreviewBackgroundLoading: new Set(),
  ftpPreviewCache: new Map(),
  backgroundFtpPreviewTimer: 0,
  backgroundFtpPreviewLimit: 1,
  photoSourcesLoaded: new Set(),
  ftpEnabled: true,
  backgroundFtpLookupTimer: 0,
  backgroundFtpLookupKey: "",
  backgroundFtpLookupRequestId: 0,
  processing: {},
  slotRevisions: new Map(),
  userSelectedSlotSources: new Set(),
  slotUploadRequestId: 0,
  processStatusTimer: 0,
  processStatusStartedAt: 0,
  navigationGuardBypass: false,
  webImages: [],
  webImageSelected: new Set(),
  webImagePageUrl: "",
  webImageScanMode: ["links", "metadata"].includes(
    localStorage.getItem("picorg-web-image-scan-mode")
  )
    ? localStorage.getItem("picorg-web-image-scan-mode")
    : "links",
  webImageCache: new Map(),
  webImageCacheQueue: [],
  webImageCacheActive: 0,
};

const WEB_IMAGE_CACHE_LIMIT = 2;

const listLabels = {
  names: "Nazwy",
  types: "Typy",
  models: "Modele",
  colors: "Kolory",
  extras: "Dodatki",
};

const photoSourceLabels = {
  local: "lokalne",
  sql: "SQL",
  ftp: "FTP",
  all: "dane",
};

const slotGrid = document.querySelector("#slotGrid");
const slotTemplate = document.querySelector("#slotTemplate");
const productForm = document.querySelector("#productForm");
const formStatus = document.querySelector("#formStatus");
const resultOutput = document.querySelector("#resultOutput");
const resultMeta = document.querySelector("#resultMeta");
const slotCount = document.querySelector("#slotCount");
const fileIndexInfo = document.querySelector("#fileIndexInfo");
const latencyInfo = document.querySelector("#latencyInfo");
const serverInfo = document.querySelector("#serverInfo");
const versionInfo = document.querySelector("#versionInfo");
const submitButton = document.querySelector("#submitButton");
const clearButton = document.querySelector("#clearButton");
const logoutButton = document.querySelector("#logoutButton");
const themeToggleButton = document.querySelector("#themeToggleButton");
const entrySelect = document.querySelector("#entrySelect");
const findByEanButton = document.querySelector("#findByEanButton");
const findProductButton = document.querySelector("#findProductButton");
const webImagesButton = document.querySelector("#webImagesButton");
const webImageUrl = document.querySelector("#webImageUrl");
const scanWebImagesButton = document.querySelector("#scanWebImagesButton");
const webImagesModal = document.querySelector("#webImagesModal");
const webImagesStatus = document.querySelector("#webImagesStatus");
const webImagesOutput = document.querySelector("#webImagesOutput");
const webImageScanMode = document.querySelector("#webImageScanMode");
const webImageMinWidth = document.querySelector("#webImageMinWidth");
const webImageMinHeight = document.querySelector("#webImageMinHeight");
const webImageMinKb = document.querySelector("#webImageMinKb");
const webImageUrlFilter = document.querySelector("#webImageUrlFilter");
const webImageHideThumbnails = document.querySelector("#webImageHideThumbnails");
const browserExtensionDownload = document.querySelector("#browserExtensionDownload");
const browserExtensionHelpButton = document.querySelector("#browserExtensionHelpButton");
const browserExtensionHelp = document.querySelector("#browserExtensionHelp");
const browserExtensionReceiveButton = document.querySelector("#browserExtensionReceiveButton");
const webImagesSelectVisibleButton = document.querySelector("#webImagesSelectVisibleButton");
const webImagesClearSelectionButton = document.querySelector("#webImagesClearSelectionButton");
const webImagesClearDataButton = document.querySelector("#webImagesClearDataButton");
const webImagesAddButton = document.querySelector("#webImagesAddButton");
const listTabs = document.querySelector("#listTabs");
const listValues = document.querySelector("#listValues");
const listAddForm = document.querySelector("#listAddForm");
const listAddInput = document.querySelector("#listAddInput");
const listStatus = document.querySelector("#listStatus");
const listUsageTitle = document.querySelector("#listUsageTitle");
const listUsageOutput = document.querySelector("#listUsageOutput");
const settingsOutput = document.querySelector("#settingsOutput");
const settingsStatus = document.querySelector("#settingsStatus");
const entryMatches = document.querySelector("#entryMatches");
const historyUserFilter = document.querySelector("#historyUserFilter");
const historyRefreshButton = document.querySelector("#historyRefreshButton");
const historyOutput = document.querySelector("#historyOutput");
const historyDetailTitle = document.querySelector("#historyDetailTitle");
const historyDetailOutput = document.querySelector("#historyDetailOutput");
const logsRefreshButton = document.querySelector("#logsRefreshButton");
const logsClearButton = document.querySelector("#logsClearButton");
const logsClearForm = document.querySelector("#logsClearForm");
const logsClearPassword = document.querySelector("#logsClearPassword");
const logsClearStatus = document.querySelector("#logsClearStatus");
const logsOutput = document.querySelector("#logsOutput");
const logsButton = document.querySelector('[data-modal="logs"]');

async function requestJson(path, options = {}) {
  const timeoutMs = Number(options.timeoutMs || 0);
  const fetchOptions = { ...options };
  delete fetchOptions.timeoutMs;
  let timeoutId = 0;
  if (timeoutMs > 0 && !fetchOptions.signal) {
    const controller = new AbortController();
    fetchOptions.signal = controller.signal;
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  let response;
  try {
    response = await fetch(path, fetchOptions);
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(
        `Backend nie odpowiedzial w ciagu ${Math.round(timeoutMs / 1000)} s (${path}). ` +
          "Jesli podales folder sieciowy albo dysk mapowany, sprawdz dostep backendu do tej lokalizacji."
      );
    }
    throw new Error(
      `Nie udalo sie polaczyc z backendem (${path}). Sprawdz, czy serwer web dziala. Szczegoly: ${
        error.message || error
      }`
    );
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = "/login";
    }
    const detail = payload.detail;
    const message =
      typeof detail === "string" ? detail : detail?.message || "Operacja nie powiodla sie.";
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  return payload;
}

function updateAdminUi() {
  state.isAdmin = state.currentUser?.role === "admin";
  document.querySelectorAll(".admin-only").forEach((node) => {
    node.style.display = state.isAdmin ? "" : "none";
  });
  if (!state.isAdmin) {
    updateLogAlert({});
  }
}

function setActiveModalNav(name = "") {
  document.querySelectorAll("[data-modal]").forEach((button) => {
    button.classList.toggle("active", button.dataset.modal === name);
  });
}

function applyTheme() {
  document.body.dataset.theme = state.theme;
  if (themeToggleButton) {
    themeToggleButton.textContent = state.theme === "dark" ? "Jasny" : "Ciemny";
  }
  localStorage.setItem("picorg-theme", state.theme);
}

function openModal(name) {
  if (!name) {
    return;
  }
  if ((name === "settings" || name === "logs") && !state.isAdmin) {
    formStatus.textContent = "Ten widok jest dostepny tylko dla administratora.";
    return;
  }
  closeAutocompletePanels();
  document.querySelector(`#${name}View`)?.classList.add("active");
  document.querySelector(`#${name}Modal`)?.classList.add("active");
  setActiveModalNav(name);
  if (name === "settings") {
    loadSettings().catch((error) => {
      settingsStatus.textContent = error.message;
    });
  }
  if (name === "history") {
    loadHistory().catch((error) => {
      historyOutput.textContent = error.message;
    });
  }
  if (name === "logs") {
    loadLogs().catch((error) => {
      logsOutput.textContent = error.message;
    });
  }
}

function closeModals() {
  document.querySelectorAll(".modal-view").forEach((modal) => modal.classList.remove("active"));
  if (logsClearPassword) logsClearPassword.value = "";
  if (logsClearStatus) logsClearStatus.textContent = "";
  setActiveModalNav("");
}

function slotFileItem(value) {
  if (!value) return null;
  if (value.file || value.token || value.uploading || value.error) return value;
  return {
    file: value,
    name: value.name || "",
    size: Number(value.size || 0),
    type: value.type || "",
    token: "",
    url: "",
    thumb_url: "",
    file_version: "",
    preprocessed: false,
    cache_timing: null,
    client_preprocess_ms: 0,
    progress: 0,
    uploading: false,
    error: "",
  };
}

function slotFileObject(value) {
  return slotFileItem(value)?.file || null;
}

function slotFileName(value) {
  const item = slotFileItem(value);
  return item?.name || item?.file?.name || "plik";
}

function slotFileSize(value) {
  const item = slotFileItem(value);
  return Number(item?.size || item?.file?.size || 0);
}

function slotFileType(value) {
  const item = slotFileItem(value);
  return item?.type || item?.file?.type || "";
}

function slotFileToken(value) {
  return String(slotFileItem(value)?.token || "").trim();
}

function slotUploadProgress(value) {
  const progress = Number(slotFileItem(value)?.progress || 0);
  return Math.max(0, Math.min(100, Math.round(progress)));
}

function isSlotUploadActive(value) {
  return Boolean(slotFileItem(value)?.uploading);
}

function slotUploadError(value) {
  return String(slotFileItem(value)?.error || "").trim();
}

function fileLabel(file) {
  const item = slotFileItem(file);
  if (!item) {
    return "Brak pliku";
  }
  const kb = Math.max(1, Math.round(slotFileSize(item) / 1024));
  const base = `${slotFileName(item)} (${kb} KB)`;
  if (slotUploadError(item)) return `${base} - blad uploadu`;
  if (isSlotUploadActive(item)) return `${base} - wysylanie ${slotUploadProgress(item)}%`;
  if (slotFileToken(item)) return `${base} - w cache`;
  return base;
}

function formatDuration(ms) {
  const value = Math.max(0, Number(ms || 0));
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 10000) return `${(value / 1000).toFixed(2)} s`;
  return `${(value / 1000).toFixed(1)} s`;
}

function formatFileSize(bytes) {
  const value = Math.max(0, Number(bytes || 0));
  if (value < 1024) return `${Math.round(value)} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function webImageDimensions(image) {
  const width = Number(image?.width || 0);
  const height = Number(image?.height || 0);
  return width && height ? `${width} x ${height}` : "rozmiar nieznany";
}

function webImageFilters() {
  return {
    minWidth: Math.max(0, Number(webImageMinWidth?.value || 0)),
    minHeight: Math.max(0, Number(webImageMinHeight?.value || 0)),
    minKb: Math.max(0, Number(webImageMinKb?.value || 0)),
    urlFilter: String(webImageUrlFilter?.value || "").trim(),
    hideThumbnails: Boolean(webImageHideThumbnails?.checked),
  };
}

function isThumbnailWebImage(image) {
  const width = Number(image?.width || 0);
  const height = Number(image?.height || 0);
  return image?.kind === "thumbnail" || (width > 0 && height > 0 && Math.max(width, height) < 300);
}

function parseWebImageUrlFilter(text) {
  const parsed = { include: [], exclude: [] };
  String(text || "")
    .split(/[\s,;]+/)
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)
    .forEach((part) => {
      if (part.startsWith("!") && part.length > 1) {
        parsed.exclude.push(part.slice(1));
      } else {
        parsed.include.push(part);
      }
    });
  return parsed;
}

function webImageMatchesUrlFilter(image, text) {
  const parsed = parseWebImageUrlFilter(text);
  const haystack = `${image?.url || ""} ${image?.filename || ""} ${image?.source || ""}`.toLowerCase();
  if (parsed.exclude.some((term) => haystack.includes(term))) return false;
  if (parsed.include.some((term) => !haystack.includes(term))) return false;
  return true;
}

function webImagePassesFilters(image, filters = webImageFilters()) {
  const width = Number(image?.width || 0);
  const height = Number(image?.height || 0);
  const kb = Number(image?.size_bytes || 0) / 1024;
  const unknownPasses = state.webImageScanMode === "links";
  if (!webImageMatchesUrlFilter(image, filters.urlFilter)) return false;
  if (filters.minWidth && width && width < filters.minWidth) return false;
  if (filters.minWidth && !width && !unknownPasses) return false;
  if (filters.minHeight && height && height < filters.minHeight) return false;
  if (filters.minHeight && !height && !unknownPasses) return false;
  if (filters.minKb && kb && kb < filters.minKb) return false;
  if (filters.minKb && !kb && !unknownPasses) return false;
  if (filters.hideThumbnails && isThumbnailWebImage(image)) return false;
  return true;
}

function visibleWebImageEntries() {
  const filters = webImageFilters();
  return (state.webImages || [])
    .map((image, index) => ({ image, index }))
    .filter((entry) => webImagePassesFilters(entry.image, filters));
}

function webImageCacheKey(image) {
  return String(image?.url || "").trim();
}

function webImageCacheEntry(image) {
  return state.webImageCache.get(webImageCacheKey(image)) || null;
}

function webImageCacheLabel(image) {
  const entry = webImageCacheEntry(image);
  if (!entry) return "";
  if (entry.status === "queued") return "oczekuje";
  if (entry.status === "loading") return "pobieranie";
  if (entry.status === "ready") return "w cache";
  if (entry.status === "error") return "blad cache";
  return "";
}

function queueWebImageCache(image, prefix = "web", { retry = false, render = true } = {}) {
  const key = webImageCacheKey(image);
  if (!key) return null;
  const existing = state.webImageCache.get(key);
  if (existing && existing.status !== "error") return existing;
  if (existing && existing.status === "error" && !retry) return existing;
  const entry = {
    status: "queued",
    payload: null,
    error: "",
    promise: null,
  };
  state.webImageCache.set(key, entry);
  state.webImageCacheQueue.push({ key, image, prefix });
  pumpWebImageCacheQueue();
  if (render) {
    renderWebImagesPicker();
  }
  return entry;
}

function pumpWebImageCacheQueue() {
  while (state.webImageCacheActive < WEB_IMAGE_CACHE_LIMIT && state.webImageCacheQueue.length) {
    const task = state.webImageCacheQueue.shift();
    const entry = state.webImageCache.get(task.key);
    if (!entry || entry.status !== "queued") continue;
    state.webImageCacheActive += 1;
    entry.status = "loading";
    entry.promise = cacheWebImageForSlot(task.image, task.prefix)
      .then((payload) => {
        entry.status = "ready";
        entry.payload = payload;
        entry.error = "";
        return payload;
      })
      .catch((error) => {
        entry.status = "error";
        entry.error = error.message || String(error);
        throw error;
      })
      .finally(() => {
        state.webImageCacheActive = Math.max(0, state.webImageCacheActive - 1);
        renderWebImagesPicker();
        pumpWebImageCacheQueue();
      });
    entry.promise.catch(() => {});
    renderWebImagesPicker();
  }
}

async function cachedWebImagePayload(image, prefix) {
  let entry = webImageCacheEntry(image);
  if (!entry || entry.status === "error") {
    entry = queueWebImageCache(image, prefix, { retry: true });
  }
  if (!entry) {
    throw new Error("Nie udalo sie przygotowac cache zdjecia.");
  }
  if (entry.payload) {
    return entry.payload;
  }
  if (entry.promise) {
    return entry.promise;
  }
  pumpWebImageCacheQueue();
  if (entry.promise) {
    return entry.promise;
  }
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (entry.payload) {
        window.clearInterval(timer);
        resolve(entry.payload);
      } else if (entry.status === "error") {
        window.clearInterval(timer);
        reject(new Error(entry.error || "Nie udalo sie pobrac zdjecia."));
      } else if (Date.now() - started > 60000) {
        window.clearInterval(timer);
        reject(new Error("Przekroczono czas oczekiwania na pobranie zdjecia."));
      }
    }, 200);
  });
}

function openWebImagesModal() {
  webImagesModal?.classList.add("active");
  webImageUrl?.focus();
}

function closeWebImagesModal() {
  webImagesModal?.classList.remove("active");
}

function clearLoadedWebImages() {
  state.webImages = [];
  state.webImageSelected.clear();
  state.webImagePageUrl = "";
  state.webImageCache.clear();
  state.webImageCacheQueue = [];
  state.webImageCacheActive = 0;
  if (webImagesStatus) {
    webImagesStatus.textContent = "";
  }
  if (webImagesOutput) {
    webImagesOutput.textContent = "Brak pobranych zdjec.";
    webImagesOutput.classList.add("empty-state");
  }
  formStatus.textContent = "Wyczyszczono wczytane zdjecia WWW.";
}

function renderWebImagesPicker() {
  if (!webImagesOutput) return;
  const visible = visibleWebImageEntries();
  const selectedVisible = visible.filter((entry) => state.webImageSelected.has(entry.index)).length;
  if (webImagesStatus) {
    webImagesStatus.textContent = `${selectedVisible}/${visible.length} zaznaczonych, ${state.webImages.length} wykrytych`;
  }
  webImagesOutput.textContent = "";
  webImagesOutput.classList.toggle("empty-state", !visible.length);
  if (!visible.length) {
    webImagesOutput.textContent = state.webImages.length
      ? "Filtry ukryly wszystkie zdjecia."
      : "Brak pobranych zdjec.";
    return;
  }
  for (const { image, index } of visible) {
    const card = document.createElement("article");
    const preview = document.createElement("div");
    const img = document.createElement("img");
    const checkbox = document.createElement("input");
    const meta = document.createElement("div");
    const title = document.createElement("strong");
    const dimensions = document.createElement("span");
    const size = document.createElement("span");
    const format = document.createElement("span");
    const source = document.createElement("span");
    const cache = document.createElement("span");
    checkbox.type = "checkbox";
    checkbox.checked = state.webImageSelected.has(index);
    checkbox.setAttribute("aria-label", `Wybierz obraz ${image.filename || index + 1}`);
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = "";
    img.src = image.url;
    preview.className = "web-image-preview";
    preview.append(checkbox, img);
    title.textContent = image.filename || `Obraz ${index + 1}`;
    dimensions.textContent = webImageDimensions(image);
    size.textContent = formatFileSize(image.size_bytes || 0);
    format.textContent = image.mime_type || "format nieznany";
    source.textContent = isThumbnailWebImage(image) ? "miniatura" : image.source || "obraz";
    cache.textContent = webImageCacheLabel(image);
    meta.className = "web-image-meta";
    meta.append(title, dimensions, format, size, source);
    if (cache.textContent) {
      meta.append(cache);
    }
    card.className = `web-image-card ${checkbox.checked ? "selected" : ""}`;
    card.title = image.url;
    card.append(preview, meta);
    const setSelected = (selected) => {
      if (selected) {
        state.webImageSelected.add(index);
        queueWebImageCache(image, "web");
      } else {
        state.webImageSelected.delete(index);
      }
      checkbox.checked = selected;
      card.classList.toggle("selected", selected);
      renderWebImagesPicker();
    };
    checkbox.addEventListener("change", () => setSelected(checkbox.checked));
    card.addEventListener("click", (event) => {
      if (event.target === checkbox) return;
      setSelected(!state.webImageSelected.has(index));
    });
    webImagesOutput.appendChild(card);
  }
}

function webImagesErrorHelp(message) {
  const text = String(message || "");
  if (/cloudflare|challenge\s*403/i.test(text)) {
    return [
      "Strona pokazuje zabezpieczenie Cloudflare/challenge 403.",
      "Importer nie dostaje wtedy HTML-a produktu, tylko strone blokady, wiec nie ma z czego wyciagnac linkow do zdjec.",
      "To zwykle wymaga sesji prawdziwej przegladarki albo cookies z tej strony.",
    ];
  }
  if (/403|forbidden/i.test(text)) {
    return [
      "Serwer odrzucil pobieranie strony kodem 403 Forbidden.",
      "Najczesciej oznacza to blokade botow, brak wymaganej sesji albo ograniczenie hotlinkowania.",
    ];
  }
  if (/html/i.test(text)) {
    return [
      "Podany adres nie zwrocil strony HTML produktu.",
      "Importer potrzebuje strony z linkami do obrazow albo bezposrednich linkow do plikow graficznych.",
    ];
  }
  return ["Nie udalo sie pobrac listy zdjec z podanego adresu."];
}

function renderWebImagesError(error) {
  const message = error?.message || String(error || "Operacja nie powiodla sie.");
  state.webImages = [];
  state.webImageSelected.clear();
  state.webImageCache.clear();
  state.webImageCacheQueue = [];
  state.webImageCacheActive = 0;
  openWebImagesModal();
  if (webImagesStatus) {
    webImagesStatus.textContent = "Nie mozna pobrac zdjec";
  }
  if (!webImagesOutput) {
    return;
  }
  webImagesOutput.textContent = "";
  webImagesOutput.classList.add("empty-state");
  const wrapper = document.createElement("div");
  const title = document.createElement("strong");
  const details = document.createElement("span");
  wrapper.className = "web-image-error";
  title.textContent = message;
  details.textContent = webImagesErrorHelp(message).join(" ");
  wrapper.append(title, details);
  webImagesOutput.appendChild(wrapper);
}

async function scanWebImages() {
  const url = webImageUrl?.value?.trim() || "";
  if (!url) {
    formStatus.textContent = "Wklej link do strony ze zdjeciami.";
    return;
  }
  state.webImageScanMode = webImageScanMode?.value || "links";
  localStorage.setItem("picorg-web-image-scan-mode", state.webImageScanMode);
  scanWebImagesButton.disabled = true;
  scanWebImagesButton.textContent = "Pobieranie...";
  formStatus.textContent =
    state.webImageScanMode === "links"
      ? "Skanowanie linkow do zdjec..."
      : "Skanowanie strony i pobieranie metadanych zdjec...";
  try {
    const payload = await requestJson("/api/web-images/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        mode: state.webImageScanMode,
        filters: webImageFilters(),
      }),
      timeoutMs: 60000,
    });
    state.webImagePageUrl = payload.source_url || url;
    state.webImageScanMode = payload.mode || state.webImageScanMode;
    state.webImages = payload.images || [];
    state.webImageSelected.clear();
    state.webImageCache.clear();
    state.webImageCacheQueue = [];
    state.webImageCacheActive = 0;
    openWebImagesModal();
    renderWebImagesPicker();
    formStatus.textContent =
      state.webImageScanMode === "links"
        ? `Wykryto ${state.webImages.length} linkow do zdjec ze strony.`
        : `Wykryto ${state.webImages.length} zdjec spelniajacych warunki.`;
  } catch (error) {
    formStatus.textContent = error.message;
    renderWebImagesError(error);
  } finally {
    scanWebImagesButton.disabled = false;
    scanWebImagesButton.textContent = "Pobierz zdjecia";
  }
}

function freeSlotPrefixes(limit = Infinity) {
  const prefixes = [];
  for (const slot of state.slots || []) {
    if (isSlotFreeForNewFile(slot.prefix)) {
      prefixes.push(slot.prefix);
      if (prefixes.length >= limit) break;
    }
  }
  return prefixes;
}

function webImageCacheItem(prefix, image, payload) {
  return {
    id: ++state.slotUploadRequestId,
    prefix,
    file: null,
    name: payload.name || image.filename || "web-image.jpg",
    size: Number(payload.size_bytes || image.size_bytes || 0),
    type: image.mime_type || "image/jpeg",
    token: payload.token || "",
    url: payload.url || "",
    thumb_url: payload.thumb_url || "",
    file_version: payload.file_version || "",
    preprocessed: Boolean(payload.preprocessed),
    cache_timing: payload.timing || null,
    client_preprocess_ms: 0,
    progress: 100,
    uploading: false,
    error: "",
    xhr: null,
    provisional: false,
    placementBlocked: false,
  };
}

async function cacheWebImageForSlot(image, prefix) {
  return requestJson("/api/web-images/cache", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: image.url,
      page_url: state.webImagePageUrl || webImageUrl?.value?.trim() || "",
      prefix,
    }),
    timeoutMs: 60000,
  });
}

async function addSelectedWebImagesToSlots() {
  const selected = [...state.webImageSelected]
    .sort((a, b) => a - b)
    .map((index) => state.webImages[index])
    .filter(Boolean);
  if (!selected.length) {
    formStatus.textContent = "Zaznacz zdjecia do dodania.";
    return;
  }
  const prefixes = freeSlotPrefixes(selected.length);
  if (!prefixes.length) {
    warnNoFreeSlots(selected.map((image) => image.filename || image.url));
    return;
  }
  webImagesAddButton.disabled = true;
  webImagesAddButton.textContent = "Dodawanie...";
  const assigned = [];
  try {
    const limit = Math.min(selected.length, prefixes.length);
    for (let index = 0; index < limit; index += 1) {
      const image = selected[index];
      const prefix = prefixes[index];
      formStatus.textContent = `Pobieranie zdjecia ${index + 1}/${limit} do slotu ${prefix}...`;
      const payload = await cachedWebImagePayload(image, prefix);
      if (!payload.token) {
        throw new Error("Backend nie zwrocil tokenu cache dla zdjecia.");
      }
      state.files.set(prefix, webImageCacheItem(prefix, image, payload));
      state.webImageSelected.delete(state.webImages.indexOf(image));
      assigned.push(prefix);
      renderSlot(prefix);
    }
    if (assigned.length) {
      formStatus.textContent = `Dodano ${assigned.length} zdjec do slotow: ${assigned.join(", ")}.`;
      updateSubmitButtonState();
    }
    if (selected.length > prefixes.length) {
      warnNoFreeSlots(selected.slice(prefixes.length).map((image) => image.filename || image.url));
    }
    renderWebImagesPicker();
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    webImagesAddButton.disabled = false;
    webImagesAddButton.textContent = "Dodaj do wolnych slotow";
  }
}

function imageFromBrowserExtensionItem(item) {
  const cache = item?.cache || {};
  return {
    url: item?.source_url || cache.url || "",
    filename: item?.filename || cache.name || "web-image.jpg",
    width: Number(item?.width || cache.width || 0),
    height: Number(item?.height || cache.height || 0),
    size_bytes: Number(item?.size_bytes || cache.size_bytes || 0),
    mime_type: item?.mime_type || "image/jpeg",
    source: item?.source || "browser-extension",
    kind: item?.kind || "image",
    page_url: item?.page_url || "",
  };
}

function loadBrowserExtensionItems(items) {
  const imported = [];
  for (const item of items || []) {
    const image = imageFromBrowserExtensionItem(item);
    if (!image.url) continue;
    imported.push(image);
    state.webImageCache.set(webImageCacheKey(image), {
      status: "ready",
      payload: item.cache || item,
      error: "",
      promise: null,
    });
  }
  if (!imported.length) {
    return 0;
  }
  state.webImagePageUrl = imported[0]?.page_url || state.webImagePageUrl || "";
  state.webImages = imported;
  state.webImageSelected = new Set(imported.map((_image, index) => index));
  openWebImagesModal();
  renderWebImagesPicker();
  return imported.length;
}

async function receiveBrowserExtensionImages() {
  if (!browserExtensionReceiveButton) return;
  browserExtensionReceiveButton.disabled = true;
  browserExtensionReceiveButton.textContent = "Odbieranie...";
  try {
    const payload = await requestJson("/api/browser-extension/imports");
    const count = loadBrowserExtensionItems(payload.items || []);
    formStatus.textContent = count
      ? `Odebrano ${count} zdjec z rozszerzenia.`
      : "Brak nowych zdjec z rozszerzenia.";
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    browserExtensionReceiveButton.disabled = false;
    browserExtensionReceiveButton.textContent = "Odbierz z rozszerzenia";
  }
}

async function downloadBrowserExtension() {
  if (!browserExtensionDownload) return;
  browserExtensionDownload.disabled = true;
  browserExtensionDownload.textContent = "Pobieranie...";
  try {
    const response = await fetch("/api/browser-extension/download", {
      cache: "no-store",
    });
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok || !contentType.includes("application/zip")) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(
        payload.detail ||
          "Backend nie zwrocil paczki ZIP rozszerzenia. Sprawdz, czy EXE zawiera folder browser_extension."
      );
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "picorgftp-sql-browser-extension.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    formStatus.textContent = "Pobrano paczke rozszerzenia.";
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    browserExtensionDownload.disabled = false;
    browserExtensionDownload.textContent = "Pobierz rozszerzenie";
  }
}

function currentProcessingSettings() {
  return state.settings?.processing || state.processing || {};
}

function uploadProcessingMode() {
  return currentProcessingSettings().upload_processing_mode || "save";
}

function showTimingDetails() {
  return Boolean(currentProcessingSettings().show_timing_details);
}

function updateRuntimeMetrics() {
  if (fileIndexInfo) {
    fileIndexInfo.textContent = state.fileIndex?.label || "";
    fileIndexInfo.title = state.fileIndex?.error || "";
  }
  if (latencyInfo) {
    latencyInfo.textContent =
      state.lastLookupMs === null ? "" : `ostatnie wczytanie: ${Math.round(state.lastLookupMs)} ms`;
  }
}

function formValue(name) {
  return productForm.elements[name]?.value?.trim() || "";
}

function currentFormPayload() {
  return {
    name: formValue("name"),
    type_name: formValue("type_name"),
    model: formValue("model"),
    color1: formValue("color1"),
    color2: formValue("color2"),
    color3: formValue("color3"),
    extra: formValue("extra"),
  };
}

function uniqueValues(values, limit = 200) {
  const seen = new Set();
  const result = [];
  for (const value of values || []) {
    const text = String(value || "").trim();
    if (!text) continue;
    const key = text.toUpperCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(text);
    if (result.length >= limit) break;
  }
  return result;
}

function setOptions(datalistId, values) {
  const datalist = document.querySelector(datalistId);
  datalist.textContent = "";
  for (const value of values || []) {
    const option = document.createElement("option");
    option.value = value;
    datalist.appendChild(option);
  }
}

function renderDatalists() {
  setOptions("#namesList", state.lists.names);
  setOptions("#typesList", state.lists.types);
  setOptions("#modelsList", state.lists.models);
  setOptions("#colorsList", state.lists.colors);
  setOptions("#extrasList", state.lists.extras);
}

const fieldListKey = {
  name: "names",
  type_name: "types",
  model: "models",
  color1: "colors",
  color2: "colors",
  color3: "colors",
  extra: "extras",
};

const fieldListLabels = {
  name: "Nazwa",
  type_name: "Typ",
  model: "Model",
  color1: "Kolor 1",
  color2: "Kolor 2",
  color3: "Kolor 3",
  extra: "Dodatek",
};

const defaultColorFieldLabels = {
  color1: "Kolor 1",
  color2: "Kolor 2",
  color3: "Kolor 3",
};

function cleanDisplayLabel(value) {
  return String(value || "")
    .trim()
    .replace(/[:*]+$/g, "")
    .trim();
}

function productFieldLabel(fieldName) {
  if (fieldName in defaultColorFieldLabels) {
    return cleanDisplayLabel(state.colorFieldLabels?.[fieldName]) || defaultColorFieldLabels[fieldName];
  }
  return fieldListLabels[fieldName] || fieldName;
}

function applyProductFieldLabels() {
  for (const fieldName of Object.keys(defaultColorFieldLabels)) {
    const node = document.querySelector(`[data-product-field-label="${fieldName}"]`);
    if (node) {
      node.textContent = productFieldLabel(fieldName);
    }
  }
}

function listHasValue(listKey, value) {
  const normalized = normalizeListValue(value);
  if (!normalized) return true;
  return (state.lists[listKey] || []).some((item) => normalizeListValue(item) === normalized);
}

function canonicalListValue(listKey, value) {
  const normalized = normalizeListValue(value);
  return (state.lists[listKey] || []).find((item) => normalizeListValue(item) === normalized) || "";
}

async function addValueToList(listKey, value) {
  const payload = await requestJson(`/api/lists/${listKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  state.lists = payload.lists || {};
  state.entries = payload.entries || state.entries;
  renderDatalists();
  renderListEditor();
  return canonicalListValue(listKey, value);
}

async function promptAddProductFieldToList(fieldName, { force = false } = {}) {
  const listKey = fieldListKey[fieldName];
  const input = productForm.elements[fieldName];
  const value = input?.value?.trim() || "";
  if (!listKey || !value || listHasValue(listKey, value)) {
    return false;
  }
  const promptKey = `${listKey}|${normalizeListValue(value)}`;
  if (state.activeListPromptKeys.has(promptKey)) {
    return false;
  }
  if (!force && state.declinedListPrompts.has(promptKey)) {
    return false;
  }
  state.activeListPromptKeys.add(promptKey);
  try {
    const label = productFieldLabel(fieldName);
    const listLabel = listLabels[listKey] || listKey;
    const shouldAdd = window.confirm(
      `${label}: "${value}" nie istnieje na liscie ${listLabel}. Dodac ten wpis do listy?`
    );
    if (!shouldAdd) {
      state.declinedListPrompts.add(promptKey);
      return false;
    }
    const canonical = await addValueToList(listKey, value);
    if (canonical) {
      input.value = canonical;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
    state.declinedListPrompts.delete(promptKey);
    formStatus.textContent = `Dodano "${canonical || value}" do listy ${listLabel}.`;
    return true;
  } finally {
    state.activeListPromptKeys.delete(promptKey);
  }
}

async function ensureProductListValues() {
  for (const fieldName of Object.keys(fieldListKey)) {
    await promptAddProductFieldToList(fieldName);
  }
}

function entryMatchesContext(entry, fieldName) {
  const payload = currentFormPayload();
  if (["type_name", "model", "color1", "color2", "color3", "extra"].includes(fieldName)) {
    if (payload.name && String(entry.name || "").toUpperCase() !== payload.name.toUpperCase()) return false;
  }
  if (["model", "color1", "color2", "color3", "extra"].includes(fieldName)) {
    if (payload.type_name && String(entry.type_name || "").toUpperCase() !== payload.type_name.toUpperCase()) return false;
  }
  if (["color1", "color2", "color3", "extra"].includes(fieldName)) {
    if (payload.model && String(entry.model || "").toUpperCase() !== payload.model.toUpperCase()) return false;
  }
  return true;
}

function localSuggestions(fieldName) {
  const existing = [];
  for (const entry of state.entries || []) {
    if (!entryMatchesContext(entry, fieldName)) continue;
    if (fieldName === "name") existing.push(entry.name);
    if (fieldName === "type_name") existing.push(entry.type_name);
    if (fieldName === "model") existing.push(entry.model);
    if (["color1", "color2", "color3"].includes(fieldName)) {
      existing.push(entry.color1, entry.color2, entry.color3);
    }
    if (fieldName === "extra") existing.push(entry.extra);
  }
  const listValues = state.lists[fieldListKey[fieldName]] || [];
  return uniqueValues([...existing, ...listValues]);
}

async function remoteSuggestions(fieldName) {
  const params = new URLSearchParams({ field: fieldName, ...currentFormPayload() });
  const payload = await requestJson(`/api/suggestions?${params.toString()}`);
  state.fileIndex = payload.file_index || state.fileIndex;
  updateRuntimeMetrics();
  return payload.values || [];
}

let activeAutocompletePanel = null;

function closeAutocompletePanels(exceptPanel = null) {
  activeAutocompletePanel = exceptPanel;
  document.querySelectorAll(".autocomplete-panel").forEach((panel) => {
    if (panel !== exceptPanel) panel.classList.remove("active");
  });
}

function renderAutocompletePanel(input, panel, values) {
  if (activeAutocompletePanel && activeAutocompletePanel !== panel && document.activeElement !== input) {
    return;
  }
  closeAutocompletePanels(panel);
  const typed = input.value.trim().toUpperCase();
  const filtered = values.filter((value) => !typed || value.toUpperCase().includes(typed)).slice(0, 200);
  panel.textContent = "";
  if (!filtered.length) {
    panel.classList.remove("active");
    return;
  }
  for (const value of filtered) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = value;
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      closeAutocompletePanels();
    });
    panel.appendChild(button);
  }
  panel.classList.add("active");
  activeAutocompletePanel = panel;
}

function setupAutocomplete() {
  productForm.setAttribute("autocomplete", "off");
  for (const fieldName of Object.keys(fieldListKey)) {
    const input = productForm.elements[fieldName];
    if (!input) continue;
    input.removeAttribute("list");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("data-lpignore", "true");
    input.setAttribute("data-1p-ignore", "true");
    input.setAttribute("data-bwignore", "true");
    input.setAttribute("data-form-type", "other");
    input.setAttribute("readonly", "readonly");
    const host = input.closest("label");
    if (!host) continue;
    host.classList.add("autocomplete-host");
    const panel = document.createElement("div");
    panel.className = "autocomplete-panel";
    host.appendChild(panel);
    let requestId = 0;
    let remoteTimer = 0;
    const unlockBrowserAutofill = () => {
      input.removeAttribute("readonly");
      window.setTimeout(() => input.setAttribute("autocomplete", "off"), 0);
    };
    const refresh = () => {
      activeAutocompletePanel = panel;
      closeAutocompletePanels(panel);
      const local = localSuggestions(fieldName);
      renderAutocompletePanel(input, panel, local);
      const currentRequest = ++requestId;
      window.clearTimeout(remoteTimer);
      remoteTimer = window.setTimeout(() => {
        remoteSuggestions(fieldName)
          .then((values) => {
            if (currentRequest === requestId && activeAutocompletePanel === panel) {
              renderAutocompletePanel(input, panel, uniqueValues([...values, ...local]));
            }
          })
          .catch(() => {});
      }, 180);
    };
    input.addEventListener("mousedown", unlockBrowserAutofill);
    input.addEventListener("focus", unlockBrowserAutofill);
    input.addEventListener("focus", refresh);
    input.addEventListener("input", refresh);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeAutocompletePanels();
    });
  }
  document.addEventListener("mousedown", (event) => {
    if (!event.target.closest(".autocomplete-host")) closeAutocompletePanels();
  });
}

function renderEntrySelect(entries = state.entries) {
  entrySelect.textContent = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = entries.length ? "Wybierz wpis" : "Brak dopasowan";
  entrySelect.appendChild(empty);
  for (const entry of entries) {
    const option = document.createElement("option");
    option.value = entry.product_id || entry.ean;
    option.textContent = entry.label;
    option.dataset.entry = JSON.stringify(entry);
    entrySelect.appendChild(option);
  }
}

function renderEntryModal(entries) {
  entryMatches.textContent = "";
  if (!entries.length) {
    entryMatches.textContent = "Brak dopasowanych wpisow.";
    document.querySelector("#entryModal").classList.add("active");
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("article");
    row.className = "entry-match";
    const text = document.createElement("div");
    const title = document.createElement("strong");
    const details = document.createElement("span");
    const button = document.createElement("button");
    title.textContent = entry.label;
    details.textContent = `${entry.product_id || "BRAK-ID"} | ${entry.ean || "BRAK-EAN"}`;
    button.type = "button";
    button.textContent = "Wczytaj";
    button.addEventListener("click", () => {
      fillForm(entry, { loadPhotos: true });
      closeModals();
    });
    text.append(title, details);
    row.append(text, button);
    entryMatches.appendChild(row);
  }
  document.querySelector("#entryModal").classList.add("active");
}

function renderListUsageModal(value, usedBy = []) {
  if (!listUsageTitle || !listUsageOutput) {
    return;
  }
  listUsageTitle.textContent = `Nie usunieto: ${value}`;
  listUsageOutput.textContent = "";
  if (!usedBy.length) {
    listUsageOutput.textContent = "Backend nie zwrocil listy produktow.";
    document.querySelector("#listUsageModal")?.classList.add("active");
    return;
  }
  for (const item of usedBy) {
    const row = document.createElement("article");
    const text = document.createElement("div");
    const title = document.createElement("strong");
    const details = document.createElement("span");
    row.className = "entry-match";
    title.textContent = item.label || `${item.name || ""} ${item.type_name || ""} ${item.model || ""}`.trim();
    details.textContent = `${item.product_id || "BRAK-ID"} | EAN ${item.ean || "BRAK-EAN"} | ${
      item.fields || "pole"
    }`;
    text.append(title, details);
    row.appendChild(text);
    listUsageOutput.appendChild(row);
  }
  document.querySelector("#listUsageModal")?.classList.add("active");
}

const trackedProductFields = [
  "name",
  "type_name",
  "model",
  "color1",
  "color2",
  "color3",
  "extra",
  "ean",
];

function updateFieldWarnings() {
  for (const fieldName of trackedProductFields) {
    const input = productForm.elements[fieldName];
    if (!input) continue;
    const label = input.closest("label");
    if (!label) continue;
    let warning = label.querySelector(".field-warning");
    if (!warning) {
      warning = document.createElement("span");
      warning.className = "field-warning";
      label.appendChild(warning);
    }
    const original = state.loadedEntryOriginal ? String(state.loadedEntryOriginal[fieldName] || "") : "";
    const current = String(input.value || "");
    const changed = Boolean(state.loadedEntryOriginal) && current !== original;
    label.classList.toggle("field-changed", changed);
    warning.textContent = "";
    warning.classList.toggle("active", changed);
    if (changed) {
      const text = document.createElement("span");
      const undo = document.createElement("button");
      text.textContent = `Bylo: ${original || "(puste)"}`;
      undo.type = "button";
      undo.textContent = "Cofnij";
      undo.addEventListener("click", () => {
        input.value = original;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        updateFieldWarnings();
      });
      warning.append(text, undo);
    }
  }
  updateSubmitButtonState();
}

function setupFieldChangeTracking() {
  for (const fieldName of trackedProductFields) {
    productForm.elements[fieldName]?.addEventListener("input", updateFieldWarnings);
  }
}

function defaultSlotSource(photo) {
  if (photo?.local && photo?.token) return "local";
  if (photo?.ftp && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  return "";
}

function selectedSlotSource(prefix, photo) {
  const selected = state.slotSources.get(prefix);
  if (selected === "local" && photo?.token) return "local";
  if (selected === "ftp" && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  return defaultSlotSource(photo);
}

function selectedPhotoToken(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  if (source === "ftp") return photo?.ftp_token || "";
  return photo?.token || "";
}

function transferableSlotSource(prefix, photo) {
  const selected = state.slotSources.get(prefix);
  if (selected === "local" && photo?.token) return "local";
  if (selected === "ftp" && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  if (photo?.token) return "local";
  if (photo?.ftp_token || photo?.ftp_filename) return "ftp";
  return "";
}

function transferablePhotoToken(photo, prefix) {
  const source = transferableSlotSource(prefix, photo);
  if (source === "ftp") return photo?.ftp_token || "";
  if (source === "local") return photo?.token || "";
  return "";
}

function revokeFilePreviewUrl(prefix) {
  const url = state.filePreviewUrls.get(prefix);
  if (url) URL.revokeObjectURL(url);
  state.filePreviewUrls.delete(prefix);
}

function filePreviewUrl(prefix, file) {
  const item = slotFileItem(file);
  const rawFile = slotFileObject(item);
  if (!rawFile) {
    return item?.url || item?.thumb_url || "";
  }
  const current = state.filePreviewUrls.get(prefix);
  if (current) return current;
  const url = URL.createObjectURL(rawFile);
  state.filePreviewUrls.set(prefix, url);
  return url;
}

function isFileImageLike(file) {
  const name = String(slotFileName(file) || "").toLowerCase();
  return (
    String(slotFileType(file) || "").startsWith("image/") ||
    [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".psd", ".eps", ".ai"].some((ext) =>
      name.endsWith(ext)
    )
  );
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

function fittedImageDataUrl(image) {
  const sourceWidth = image.naturalWidth || image.width;
  const sourceHeight = image.naturalHeight || image.height;
  if (!sourceWidth || !sourceHeight) return "";
  const detectScale = Math.min(1, 512 / Math.max(sourceWidth, sourceHeight));
  const detectWidth = Math.max(1, Math.round(sourceWidth * detectScale));
  const detectHeight = Math.max(1, Math.round(sourceHeight * detectScale));
  const detect = document.createElement("canvas");
  detect.width = detectWidth;
  detect.height = detectHeight;
  const detectCtx = detect.getContext("2d", { willReadFrequently: true });
  detectCtx.drawImage(image, 0, 0, detectWidth, detectHeight);
  const pixels = detectCtx.getImageData(0, 0, detectWidth, detectHeight).data;
  const cornerSize = Math.max(1, Math.min(detectWidth, detectHeight, Math.floor(Math.min(detectWidth, detectHeight) / 20) || 1));
  const corners = [
    [0, 0],
    [detectWidth - cornerSize, 0],
    [0, detectHeight - cornerSize],
    [detectWidth - cornerSize, detectHeight - cornerSize],
  ];
  const bg = [0, 0, 0, 0];
  let bgCount = 0;
  for (const [startX, startY] of corners) {
    for (let y = startY; y < startY + cornerSize; y += 1) {
      for (let x = startX; x < startX + cornerSize; x += 1) {
        const idx = (y * detectWidth + x) * 4;
        bg[0] += pixels[idx];
        bg[1] += pixels[idx + 1];
        bg[2] += pixels[idx + 2];
        bg[3] += pixels[idx + 3];
        bgCount += 1;
      }
    }
  }
  bg[0] = bg[0] / Math.max(1, bgCount);
  bg[1] = bg[1] / Math.max(1, bgCount);
  bg[2] = bg[2] / Math.max(1, bgCount);
  bg[3] = bg[3] / Math.max(1, bgCount);
  let left = detectWidth;
  let top = detectHeight;
  let right = -1;
  let bottom = -1;
  for (let y = 0; y < detectHeight; y += 1) {
    for (let x = 0; x < detectWidth; x += 1) {
      const idx = (y * detectWidth + x) * 4;
      const alpha = pixels[idx + 3];
      const diff =
        Math.abs(pixels[idx] - bg[0]) +
        Math.abs(pixels[idx + 1] - bg[1]) +
        Math.abs(pixels[idx + 2] - bg[2]);
      const alphaDiff = Math.abs(alpha - bg[3]);
      if ((bg[3] < 250 && alpha > 8) || alphaDiff > 32 || (alpha > 8 && diff > 54)) {
        left = Math.min(left, x);
        top = Math.min(top, y);
        right = Math.max(right, x + 1);
        bottom = Math.max(bottom, y + 1);
      }
    }
  }
  if (right <= left || bottom <= top) return "";
  const areaRatio = ((right - left) * (bottom - top)) / Math.max(1, detectWidth * detectHeight);
  if (areaRatio > 0.98) return "";
  const scaleX = sourceWidth / detectWidth;
  const scaleY = sourceHeight / detectHeight;
  let cropLeft = Math.floor(left * scaleX);
  let cropTop = Math.floor(top * scaleY);
  let cropRight = Math.ceil(right * scaleX);
  let cropBottom = Math.ceil(bottom * scaleY);
  const margin = Math.ceil(Math.max(cropRight - cropLeft, cropBottom - cropTop) * 0.06);
  cropLeft = Math.max(0, cropLeft - margin);
  cropTop = Math.max(0, cropTop - margin);
  cropRight = Math.min(sourceWidth, cropRight + margin);
  cropBottom = Math.min(sourceHeight, cropBottom + margin);
  const sourceAspect = sourceWidth / Math.max(1, sourceHeight);
  let cropWidth = cropRight - cropLeft;
  let cropHeight = cropBottom - cropTop;
  if (cropWidth / cropHeight < sourceAspect) {
    const targetWidth = Math.min(sourceWidth, cropHeight * sourceAspect);
    cropLeft = Math.max(0, Math.min(sourceWidth - targetWidth, cropLeft - (targetWidth - cropWidth) / 2));
    cropWidth = targetWidth;
  } else {
    const targetHeight = Math.min(sourceHeight, cropWidth / sourceAspect);
    cropTop = Math.max(0, Math.min(sourceHeight - targetHeight, cropTop - (targetHeight - cropHeight) / 2));
    cropHeight = targetHeight;
  }
  const outScale = Math.min(1, 1200 / Math.max(sourceWidth, sourceHeight));
  const outWidth = Math.max(1, Math.round(sourceWidth * outScale));
  const outHeight = Math.max(1, Math.round(sourceHeight * outScale));
  const out = document.createElement("canvas");
  out.width = outWidth;
  out.height = outHeight;
  out
    .getContext("2d")
    .drawImage(image, cropLeft, cropTop, cropWidth, cropHeight, 0, 0, outWidth, outHeight);
  return out.toDataURL("image/jpeg", 0.9);
}

async function renderSelectedFilePreview(prefix, file, preview, previewImage, empty) {
  const url = filePreviewUrl(prefix, file);
  if (!url) {
    preview.classList.remove("thumb-loading", "has-image");
    empty.textContent = slotFileName(file);
    return;
  }
  preview.classList.add("thumb-loading");
  try {
    const image = await loadImage(url);
    if (state.files.get(prefix) !== file || !document.body.contains(preview)) return;
    const fitted = isSlotFit(prefix) ? fittedImageDataUrl(image) : "";
    previewImage.src = fitted || url;
    preview.classList.add("has-image");
    preview.classList.remove("thumb-loading");
  } catch (_error) {
    if (state.files.get(prefix) !== file || !document.body.contains(preview)) return;
    preview.classList.remove("thumb-loading", "has-image");
    empty.textContent = "Podglad niedostepny";
  }
}

function loadedFileUrl(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  if (source === "ftp" && photo?.ftp_url) return photo.ftp_url;
  if (source === "local" && photo?.url) return photo.url;
  const token = selectedPhotoToken(photo, prefix);
  return token ? `/api/file?token=${encodeURIComponent(token)}` : "";
}

async function openSlotFile(prefix) {
  const selectedFile = state.files.get(prefix);
  if (selectedFile) {
    window.open(filePreviewUrl(prefix, selectedFile), "_blank", "noopener");
    return;
  }
  let photo = state.loadedPhotos.get(prefix);
  if (selectedSlotSource(prefix, photo) === "ftp" && photo?.ftp_filename && !photo.ftp_token) {
    await loadFtpPreview(photo, prefix);
    photo = state.loadedPhotos.get(prefix);
  }
  const url = loadedFileUrl(photo, prefix);
  if (url) window.open(url, "_blank", "noopener");
}

function markSlotDeletion(prefix, photo) {
  if (!photo) return;
  state.deletedSlots.set(prefix, {
    prefix,
    token: photo.token || "",
    ftp_filename: photo.ftp_filename || "",
    sql: Boolean(photo.sql),
    filename: photo.filename || "",
    source: selectedSlotSource(prefix, photo),
  });
}

function slotStatusText(photo, prefix = "") {
  if (!photo) {
    return "Przeciagnij albo wybierz plik";
  }
  if (selectedSlotSource(prefix, photo) === "ftp" && photo.ftp_filename) {
    return `FTP: ${photo.ftp_filename}`;
  }
  if (photo.filename) {
    return photo.filename;
  }
  if (photo.ftp_filename) {
    return `FTP: ${photo.ftp_filename}`;
  }
  const parts = [];
  if (photo.local) parts.push("LOCAL");
  if (photo.ftp) parts.push("FTP");
  if (photo.sql) parts.push("SQL");
  return parts.length ? parts.join(" / ") : "Brak lokalnego pliku";
}

async function copyTextToClipboard(text, successMessage = "Skopiowano.") {
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      formStatus.textContent = successMessage;
      return;
    } catch (_error) {
      // Older LAN/browser contexts can expose clipboard but still reject writes.
    }
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.style.position = "fixed";
  field.style.left = "-9999px";
  document.body.appendChild(field);
  field.focus();
  field.select();
  document.execCommand("copy");
  field.remove();
  formStatus.textContent = successMessage;
}

function renderSlotBadges(container, photo, file, prefix) {
  const badges = document.createElement("div");
  badges.className = "slot-badges";
  const statuses = [
    ["local", "LOCAL", "Plik jest w folderze backendu"],
    ["ftp", "FTP", "Wpis dla slotu jest na FTP"],
    ["sql", "SQL", "Wpis dla slotu jest w SQL"],
  ];
  if (file) {
    const badge = document.createElement("span");
    badge.className = "slot-badge on";
    badge.title = "Nowy plik wybrany w przegladarce";
    badge.textContent = "NOWY";
    badges.appendChild(badge);
  }
  for (const [key, label, title] of statuses) {
    const sqlValue = String(photo?.sql_value || "").trim();
    const canPreview =
      (key === "local" && photo?.token) ||
      (key === "ftp" && photo?.ftp_filename);
    const canCopySql = key === "sql" && Boolean(sqlValue);
    const badge = document.createElement(canPreview || canCopySql ? "button" : "span");
    const selected = key !== "sql" && selectedSlotSource(prefix, photo) === key;
    const loading =
      isPhotoSourceLoading(key) || (key === "ftp" && state.ftpPreviewLoading.has(prefix));
    badge.dataset.source = key;
    badge.className = `slot-badge slot-badge-${key} ${photo && photo[key] ? "on" : ""} ${
      selected ? "selected" : ""
    } ${loading ? "loading" : ""}`;
    badge.title = loading
      ? sourceLoadingTitle(key)
      : canCopySql
      ? "Kliknij, aby skopiowac link z SQL"
      : selected
      ? `${title} (aktywny podglad)`
      : title;
    badge.textContent = label;
    if (canPreview || canCopySql) {
      badge.type = "button";
      badge.setAttribute("aria-pressed", selected ? "true" : "false");
      if (loading) {
        badge.setAttribute("aria-busy", "true");
      }
      badge.addEventListener("click", (event) => {
        event.stopPropagation();
        if (canCopySql) {
          copyTextToClipboard(sqlValue, `Skopiowano link SQL dla slotu ${prefix}.`).catch((error) => {
            formStatus.textContent = error.message;
          });
          return;
        }
        state.slotSources.set(prefix, key);
        state.userSelectedSlotSources.add(prefix);
        if (key === "ftp" && !photo.ftp_token) {
          if (state.ftpPreviewLoading.has(prefix)) {
            state.ftpPreviewBackgroundLoading.delete(prefix);
            updateSlotPreview(prefix);
          } else {
            loadFtpPreview(photo, prefix).catch((error) => {
              formStatus.textContent = error.message;
            });
          }
        } else {
          updateSlotPreview(prefix);
        }
      });
    }
    badges.appendChild(badge);
  }
  container.appendChild(badges);
}

function isPhotoSourceLoading(source) {
  const status = state.photoSourceStatus.get(source);
  return status === "pending" || status === "loading";
}

function sourceLoadingTitle(source) {
  if (source === "ftp") {
    return "Wczytywanie FTP";
  }
  if (source === "local") {
    return "Wczytywanie plikow lokalnych";
  }
  if (source === "sql") {
    return "Wczytywanie SQL";
  }
  return "Wczytywanie danych";
}

function photoHasUsableContent(photo) {
  if (!photo) return false;
  return Boolean(
    photo.token ||
      photo.url ||
      photo.thumb_url ||
      photo.filename ||
      photo.ftp_token ||
      photo.ftp_filename ||
      photo.ftp_url ||
      photo.ftp_thumb_url ||
      photo.sql_value ||
      photo.local ||
      photo.ftp ||
      photo.sql
  );
}

function isProvisionalSlotPlacement(prefix) {
  return Boolean(state.photosLoading && !photoHasUsableContent(state.loadedPhotos.get(prefix)));
}

function createSlotFileUpload(prefix, file, options = {}) {
  return {
    id: ++state.slotUploadRequestId,
    prefix,
    file,
    name: file?.name || "",
    size: Number(file?.size || 0),
    type: file?.type || "",
    token: "",
    url: "",
    thumb_url: "",
    file_version: "",
    preprocessed: false,
    cache_timing: null,
    client_preprocess_ms: 0,
    progress: 0,
    uploading: false,
    error: "",
    xhr: null,
    provisional: Boolean(options.provisional),
    placementBlocked: false,
  };
}

function uploadCacheErrorMessage(payload, fallback = "Nie udalo sie wyslac pliku do cache.") {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail?.message) return detail.message;
  return fallback;
}

function fileItemPrefixes(item) {
  const prefixes = [];
  for (const [prefix, current] of state.files.entries()) {
    if (current === item) prefixes.push(prefix);
  }
  return prefixes;
}

function refreshFileItemSlots(item) {
  for (const prefix of fileItemPrefixes(item)) {
    updateSlotPreview(prefix);
  }
  updateSubmitButtonState();
}

function clientTargetFormatInfo(file) {
  const settings = currentProcessingSettings();
  const sourceType = String(file?.type || "").toLowerCase();
  const sourceName = String(file?.name || "");
  const sourceExt = sourceName.split(".").pop()?.toLowerCase() || "";
  if (settings.convert_enabled) {
    const target = String(settings.target_format || "PNG").toUpperCase();
    if (target === "JPG" || target === "JPEG") return { type: "image/jpeg", ext: "jpg" };
    if (target === "PNG") return { type: "image/png", ext: "png" };
    if (target === "WEBP") return { type: "image/webp", ext: "webp" };
  }
  if (sourceType === "image/jpeg" || sourceExt === "jpg" || sourceExt === "jpeg") {
    return { type: "image/jpeg", ext: "jpg" };
  }
  if (sourceType === "image/png" || sourceExt === "png") return { type: "image/png", ext: "png" };
  if (sourceType === "image/webp" || sourceExt === "webp") return { type: "image/webp", ext: "webp" };
  return null;
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("Przegladarka nie utworzyla przetworzonego obrazu."));
        }
      },
      type,
      quality
    );
  });
}

function loadImageForProcessing(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Nie udalo sie odczytac obrazu po stronie klienta."));
    };
    image.src = url;
  });
}

async function preprocessFileOnClient(file) {
  const settings = currentProcessingSettings();
  if (uploadProcessingMode() !== "client") {
    return { file, preprocessed: false, elapsed_ms: 0 };
  }
  if (
    !settings.resize_enabled &&
    !settings.compress_enabled &&
    !settings.max_size_enabled &&
    !settings.convert_enabled
  ) {
    return { file, preprocessed: false, elapsed_ms: 0 };
  }
  const format = clientTargetFormatInfo(file);
  if (!format) {
    return { file, preprocessed: false, elapsed_ms: 0 };
  }
  const started = performance.now();
  const image = await loadImageForProcessing(file);
  const maxDim = Math.max(64, Math.min(20000, Number(settings.max_dim || 2000)));
  let width = image.naturalWidth || image.width;
  let height = image.naturalHeight || image.height;
  if (settings.resize_enabled && Math.max(width, height) > maxDim) {
    const scale = maxDim / Math.max(width, height);
    width = Math.max(1, Math.round(width * scale));
    height = Math.max(1, Math.round(height * scale));
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { alpha: format.type !== "image/jpeg" });
  if (!ctx) {
    return { file, preprocessed: false, elapsed_ms: performance.now() - started };
  }
  if (format.type === "image/jpeg") {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
  }
  ctx.drawImage(image, 0, 0, width, height);
  const qualityBase = Math.max(1, Math.min(100, Number(settings.compress_quality || 85))) / 100;
  let quality = settings.compress_enabled ? qualityBase : 0.95;
  let blob = await canvasToBlob(canvas, format.type, quality);
  if (settings.max_size_enabled && ["image/jpeg", "image/webp"].includes(format.type)) {
    const maxBytes = Math.max(1, Number(settings.max_file_kb || 500)) * 1024;
    while (blob.size > maxBytes && quality > 0.1) {
      quality = Math.max(0.1, quality - 0.05);
      blob = await canvasToBlob(canvas, format.type, quality);
    }
  }
  const sourceName = String(file.name || "upload");
  const stem = sourceName.includes(".") ? sourceName.replace(/\.[^.]+$/, "") : sourceName;
  const processed = new File([blob], `${stem}.${format.ext}`, {
    type: format.type,
    lastModified: Date.now(),
  });
  return {
    file: processed,
    preprocessed: true,
    elapsed_ms: performance.now() - started,
    original_size: file.size || 0,
  };
}

function uploadSlotFile(prefix, item) {
  const file = slotFileObject(item);
  if (!file) return;
  const requestId = item.id;
  item.uploading = true;
  item.progress = 0;
  item.error = "";
  item.token = "";
  item.url = "";
  item.thumb_url = "";
  item.file_version = "";
  item.preprocessed = false;
  item.client_preprocess_ms = 0;
  item.original_size = Number(file.size || item.size || 0);
  refreshFileItemSlots(item);
  const sendUpload = (uploadFile, clientPreprocessed = false) => {
    if (item.id !== requestId) return;
    const data = new FormData();
    data.set("prefix", prefix);
    data.set("file", uploadFile, uploadFile.name || slotFileName(item));
  const xhr = new XMLHttpRequest();
  item.xhr = xhr;
  xhr.upload.addEventListener("progress", (event) => {
    if (!event.lengthComputable) return;
    const nextProgress = Math.max(1, Math.min(99, Math.round((event.loaded / event.total) * 100)));
    if (nextProgress === item.progress) return;
    item.progress = nextProgress;
    formStatus.textContent = `Wysylanie pliku dla slotu ${prefix}: ${nextProgress}%`;
    refreshFileItemSlots(item);
  });
  xhr.addEventListener("load", () => {
    const payload = xhr.response || {};
    if (xhr.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (xhr.status < 200 || xhr.status >= 300) {
      item.uploading = false;
      item.error = uploadCacheErrorMessage(payload);
      item.xhr = null;
      formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
      refreshFileItemSlots(item);
      return;
    }
    if (!payload.token) {
      item.uploading = false;
      item.error = "Backend nie zwrocil tokenu cache.";
      item.xhr = null;
      formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
      refreshFileItemSlots(item);
      return;
    }
    item.token = payload.token || "";
    item.url = payload.url || "";
    item.thumb_url = payload.thumb_url || "";
    item.file_version = payload.file_version || "";
    item.preprocessed = Boolean(payload.preprocessed || clientPreprocessed);
    item.client_preprocess_ms = item.client_preprocess_ms || 0;
    item.cache_timing = payload.timing || null;
    item.name = payload.name || item.name;
    item.size = Number(payload.size_bytes || item.size || 0);
    item.progress = 100;
    item.uploading = false;
    item.error = "";
    item.xhr = null;
    const timingText =
      showTimingDetails() && payload.timing?.total_ms
        ? ` (${formatDuration(payload.timing.total_ms)})`
        : "";
    formStatus.textContent = `Plik dla slotu ${prefix} jest w cache${timingText}.`;
    refreshFileItemSlots(item);
  });
  xhr.addEventListener("error", () => {
    item.uploading = false;
    item.error = "Nie udalo sie polaczyc z backendem podczas uploadu.";
    item.xhr = null;
    formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
    refreshFileItemSlots(item);
  });
  xhr.addEventListener("abort", () => {
    item.uploading = false;
    item.error = "Upload przerwany.";
    item.xhr = null;
    refreshFileItemSlots(item);
  });
  xhr.open("POST", "/api/upload-cache");
  xhr.responseType = "json";
  xhr.send(data);
  };
  preprocessFileOnClient(file)
    .then((prepared) => {
      if (item.id !== requestId) return;
      item.client_preprocess_ms = Math.round(prepared.elapsed_ms || 0);
      if (prepared.preprocessed) {
        item.file = prepared.file;
        item.name = prepared.file.name || item.name;
        item.size = Number(prepared.file.size || item.size || 0);
      }
      sendUpload(prepared.file, prepared.preprocessed);
    })
    .catch((error) => {
      item.uploading = false;
      item.error = error.message || "Nie udalo sie przygotowac obrazu po stronie klienta.";
      item.xhr = null;
      formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
      refreshFileItemSlots(item);
    });
  updateSubmitButtonState();
}

function activeSlotUploads() {
  return [...state.files.entries()].filter(([, item]) => isSlotUploadActive(item));
}

function failedSlotUploads() {
  return [...state.files.entries()].filter(([, item]) => Boolean(slotUploadError(item)));
}

function ensureSlotUploadsReady() {
  const pending = activeSlotUploads();
  if (pending.length) {
    throw new Error("Poczekaj na zakonczenie wysylania plikow do cache.");
  }
  const failed = failedSlotUploads();
  if (failed.length) {
    const [prefix, item] = failed[0];
    throw new Error(`Upload slotu ${prefix} nie powiodl sie: ${slotUploadError(item)}`);
  }
}

function renderSlotUploadOverlay(preview, item) {
  preview.querySelector(".slot-upload-overlay")?.remove();
  const error = slotUploadError(item);
  if (!isSlotUploadActive(item) && !error) return;
  const overlay = document.createElement("div");
  const label = document.createElement("span");
  const line = document.createElement("div");
  const bar = document.createElement("i");
  const progress = slotUploadProgress(item);
  overlay.className = `slot-upload-overlay ${error ? "error" : ""}`;
  label.textContent = error ? "Upload nieudany" : `Wysylanie ${progress}%`;
  line.className = "progress-line upload-progress-line";
  line.style.setProperty("--upload-progress", `${progress}%`);
  line.appendChild(bar);
  overlay.append(label, line);
  preview.appendChild(overlay);
}

function setFtpBadgeLoading(prefix, loading) {
  const card = slotGrid.querySelector(`[data-slot-prefix="${prefix}"]`);
  const badge = card?.querySelector('.slot-badge-ftp[data-source="ftp"]');
  if (!badge) return;
  const selected = badge.classList.contains("selected");
  badge.classList.toggle("loading", Boolean(loading));
  if (loading) {
    badge.setAttribute("aria-busy", "true");
    badge.title = "Pobieranie miniatury FTP w tle";
  } else {
    badge.removeAttribute("aria-busy");
    badge.title = selected ? "Wpis dla slotu jest na FTP (aktywny podglad)" : "Wpis dla slotu jest na FTP";
  }
}

function slotRevision(prefix) {
  return Number(state.slotRevisions.get(prefix) || 0);
}

function bumpSlotRevision(prefix) {
  state.slotRevisions.set(prefix, slotRevision(prefix) + 1);
}

function ftpPreviewCacheKey(photo, fallbackEan = "") {
  const filename = String(photo?.ftp_filename || "").trim();
  const ean = String(photo?.ean || fallbackEan || "").trim();
  return filename && ean ? `${ean}|${filename}` : "";
}

function clearFtpPreviewCacheForPrefixes(prefixes, fallbackEan = "") {
  const prefixSet = new Set(
    [...(prefixes || [])].map((prefix) => String(prefix || "").trim()).filter(Boolean)
  );
  if (!prefixSet.size) return;
  const ean = String(fallbackEan || formValue("ean") || state.loadedEntryOriginal?.ean || "").trim();
  for (const prefix of prefixSet) {
    const photo = state.loadedPhotos.get(prefix);
    const directKey = ftpPreviewCacheKey(photo, ean);
    if (directKey) {
      state.ftpPreviewCache.delete(directKey);
    }
  }
  for (const key of Array.from(state.ftpPreviewCache.keys())) {
    const [keyEan, filename] = String(key).split("|", 2);
    if (ean && keyEan && keyEan !== ean) continue;
    for (const prefix of prefixSet) {
      if (filename?.startsWith(`${keyEan}_${prefix}.`) || filename?.includes(`_${prefix}.`)) {
        state.ftpPreviewCache.delete(key);
        break;
      }
    }
  }
}

function applyCachedFtpPreview(photo, prefix, cached) {
  if (!cached) return photo;
  if (cached.file_version && photo?.ftp_file_version && cached.file_version !== photo.ftp_file_version) {
    return photo;
  }
  return {
    ...photo,
    ftp_token: cached.token || photo?.ftp_token || "",
    ftp_url: cached.url || photo?.ftp_url || "",
    ftp_thumb_url: cached.thumb_url || photo?.ftp_thumb_url || "",
    ftp_file_version: cached.file_version || photo?.ftp_file_version || "",
  };
}

async function loadFtpPreview(photo, prefix, requestId = state.photoLoadRequestId, options = {}) {
  if (!photo?.ftp_filename || state.ftpPreviewLoading.has(prefix)) return;
  const revision = slotRevision(prefix);
  const cacheKey = ftpPreviewCacheKey(photo, formValue("ean") || "");
  const sourceBefore = selectedSlotSource(prefix, photo);
  const explicitSourceBefore = state.slotSources.get(prefix);
  const cached = cacheKey ? state.ftpPreviewCache.get(cacheKey) : null;
  if (cached) {
    const currentPhoto = state.loadedPhotos.get(prefix);
    if (
      requestId !== state.photoLoadRequestId ||
      revision !== slotRevision(prefix) ||
      !currentPhoto ||
      ftpPreviewCacheKey(currentPhoto, formValue("ean") || "") !== cacheKey
    ) {
      return;
    }
    const updated = applyCachedFtpPreview(currentPhoto, prefix, cached);
    state.loadedPhotos.set(prefix, updated);
    if (!options.background || sourceBefore === "ftp") {
      state.slotSources.set(prefix, "ftp");
    } else if (explicitSourceBefore) {
      state.slotSources.set(prefix, explicitSourceBefore);
    }
    if (options.background && selectedSlotSource(prefix, updated) !== "ftp") {
      setFtpBadgeLoading(prefix, false);
    } else {
      updateSlotPreview(prefix);
    }
    return;
  }
  state.ftpPreviewLoading.add(prefix);
  const background = Boolean(options.background);
  if (background) {
    state.ftpPreviewBackgroundLoading.add(prefix);
  } else {
    state.ftpPreviewBackgroundLoading.delete(prefix);
  }
  if (!background) {
    formStatus.textContent = `Pobieranie podgladu FTP dla slotu ${prefix}...`;
  }
  if (background) {
    setFtpBadgeLoading(prefix, true);
  } else {
    updateSlotPreview(prefix);
  }
  try {
    const payload = await requestJson("/api/ftp-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ean: photo.ean || formValue("ean") || "", filename: photo.ftp_filename }),
    });
    if (cacheKey) {
      state.ftpPreviewCache.set(cacheKey, {
        token: payload.token || "",
        url: payload.url || "",
        thumb_url: payload.thumb_url || "",
        file_version: payload.file_version || "",
      });
    }
    const currentPhoto = state.loadedPhotos.get(prefix);
    if (
      requestId !== state.photoLoadRequestId ||
      revision !== slotRevision(prefix) ||
      !currentPhoto ||
      ftpPreviewCacheKey(currentPhoto, formValue("ean") || "") !== cacheKey
    ) {
      return;
    }
    const updated = {
      ...currentPhoto,
      ftp_token: payload.token || "",
      ftp_url: payload.url || "",
      ftp_thumb_url: payload.thumb_url || "",
      ftp_file_version: payload.file_version || "",
    };
    state.loadedPhotos.set(prefix, updated);
    if (!background || sourceBefore === "ftp") {
      state.slotSources.set(prefix, "ftp");
    } else if (explicitSourceBefore) {
      state.slotSources.set(prefix, explicitSourceBefore);
    }
    if (!background) {
      formStatus.textContent = `Pobrano podglad FTP dla slotu ${prefix}.`;
    }
  } finally {
    state.ftpPreviewLoading.delete(prefix);
    state.ftpPreviewBackgroundLoading.delete(prefix);
    const currentPhoto = state.loadedPhotos.get(prefix);
    if (background && selectedSlotSource(prefix, currentPhoto) !== "ftp") {
      setFtpBadgeLoading(prefix, false);
    } else {
      updateSlotPreview(prefix);
    }
  }
}

function nextBackgroundFtpPreviewCandidate() {
  for (const slot of state.slots || []) {
    const prefix = slot.prefix;
    const photo = state.loadedPhotos.get(prefix);
    if (
      photo?.ftp &&
      photo.ftp_filename &&
      !photo.ftp_token &&
      !state.files.has(prefix) &&
      !state.deletedSlots.has(prefix) &&
      !photo?.dirty &&
      !state.ftpPreviewLoading.has(prefix)
    ) {
      return { prefix, photo };
    }
  }
  return null;
}

function scheduleBackgroundFtpPreviewLoad(requestId = state.photoLoadRequestId, delayMs = 900) {
  window.clearTimeout(state.backgroundFtpPreviewTimer);
  state.backgroundFtpPreviewTimer = window.setTimeout(() => {
    loadNextBackgroundFtpPreview(requestId).catch(() => {});
  }, delayMs);
}

async function loadNextBackgroundFtpPreview(requestId = state.photoLoadRequestId) {
  if (requestId !== state.photoLoadRequestId) {
    return;
  }
  let launched = 0;
  const limit = Math.max(1, Number(state.backgroundFtpPreviewLimit) || 1);
  while (state.ftpPreviewBackgroundLoading.size < limit) {
    const candidate = nextBackgroundFtpPreviewCandidate();
    if (!candidate) {
      break;
    }
    launched += 1;
    loadFtpPreview(candidate.photo, candidate.prefix, requestId, { background: true })
      .catch(() => {
        // Background preview loading must not block regular editing.
      })
      .finally(() => {
        if (requestId === state.photoLoadRequestId && nextBackgroundFtpPreviewCandidate()) {
          scheduleBackgroundFtpPreviewLoad(requestId, 900);
        }
      });
  }
  if (launched && requestId === state.photoLoadRequestId && nextBackgroundFtpPreviewCandidate()) {
    scheduleBackgroundFtpPreviewLoad(requestId, 900);
  }
}

function isSlotFit(prefix) {
  if (state.slotFits.has(prefix)) {
    return Boolean(state.slotFits.get(prefix));
  }
  return Boolean(state.defaultSlotFit);
}

function thumbnailUrl(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  const url =
    source === "ftp"
      ? photo?.ftp_thumb_url || photo?.ftp_url || ""
      : photo?.thumb_url || photo?.url || "";
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}fit=${isSlotFit(prefix) ? "1" : "0"}&width=260&height=180`;
}

function clearSlotAssignment(prefix, options = {}) {
  bumpSlotRevision(prefix);
  const markDelete = options.markDelete !== false;
  if (markDelete) {
    markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  }
  revokeFilePreviewUrl(prefix);
  state.files.delete(prefix);
  state.loadedPhotos.delete(prefix);
  state.slotFits.delete(prefix);
  state.slotSources.delete(prefix);
  state.userSelectedSlotSources.delete(prefix);
}

function setSlotFile(prefix, file, options = {}) {
  bumpSlotRevision(prefix);
  markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  revokeFilePreviewUrl(prefix);
  const item = createSlotFileUpload(prefix, file, {
    provisional: options.provisional ?? isProvisionalSlotPlacement(prefix),
  });
  state.files.set(prefix, item);
  state.loadedPhotos.delete(prefix);
  state.slotSources.delete(prefix);
  state.userSelectedSlotSources.delete(prefix);
  uploadSlotFile(prefix, item);
}

function getSlotAssignment(prefix) {
  if (state.files.has(prefix)) {
    return { type: "file", prefix, value: state.files.get(prefix), source: "", fit: isSlotFit(prefix) };
  }
  if (state.loadedPhotos.has(prefix)) {
    const photo = state.loadedPhotos.get(prefix);
    return {
      type: "loaded",
      prefix,
      value: photo,
      source: transferableSlotSource(prefix, photo),
      fit: isSlotFit(prefix),
    };
  }
  return null;
}

function setSlotAssignment(prefix, assignment, options = {}) {
  const sourceFit = assignment && "fit" in assignment ? Boolean(assignment.fit) : isSlotFit(assignment?.prefix || prefix);
  const sourceType = assignment?.source || "";
  clearSlotAssignment(prefix, { markDelete: options.markDelete !== false });
  if (!assignment) {
    return;
  }
  if (assignment.type === "file") {
    const item = slotFileItem(assignment.value);
    if (item) {
      item.prefix = prefix;
      item.provisional = false;
      item.placementBlocked = false;
    }
    state.files.set(prefix, item);
    state.slotFits.set(prefix, sourceFit);
    if (sourceType) state.slotSources.set(prefix, sourceType);
    state.userSelectedSlotSources.delete(prefix);
    if (item?.file && !item.token && !item.uploading && !item.error) {
      uploadSlotFile(prefix, item);
    }
    return;
  }
  if (assignment.type === "loaded") {
    state.loadedPhotos.set(prefix, { ...assignment.value, prefix, dirty: true });
    state.slotFits.set(prefix, sourceFit);
    if (sourceType) state.slotSources.set(prefix, sourceType);
    state.userSelectedSlotSources.delete(prefix);
  }
}

function moveSlotContent(sourcePrefix, targetPrefix) {
  if (!sourcePrefix || !targetPrefix || sourcePrefix === targetPrefix) {
    return;
  }
  const source = getSlotAssignment(sourcePrefix);
  if (!source) {
    return;
  }
  const target = getSlotAssignment(targetPrefix);
  if (target) {
    markSlotDeletion(targetPrefix, state.loadedPhotos.get(targetPrefix));
    markSlotDeletion(sourcePrefix, state.loadedPhotos.get(sourcePrefix));
    clearSlotAssignment(targetPrefix, { markDelete: false });
    clearSlotAssignment(sourcePrefix, { markDelete: false });
    setSlotAssignment(targetPrefix, source, { markDelete: false });
    setSlotAssignment(sourcePrefix, target, { markDelete: false });
    formStatus.textContent = `Zamieniono slot ${sourcePrefix} ze slotem ${targetPrefix}.`;
    renderSlot(targetPrefix);
    renderSlot(sourcePrefix);
    return;
  }
  markSlotDeletion(targetPrefix, state.loadedPhotos.get(targetPrefix));
  markSlotDeletion(sourcePrefix, state.loadedPhotos.get(sourcePrefix));
  setSlotAssignment(targetPrefix, source, { markDelete: false });
  clearSlotAssignment(sourcePrefix, { markDelete: false });
  formStatus.textContent = `Przeniesiono slot ${sourcePrefix} -> ${targetPrefix}.`;
  renderSlot(targetPrefix);
  renderSlot(sourcePrefix);
}

function slotIndex(prefix) {
  return (state.slots || []).findIndex((slot) => String(slot.prefix) === String(prefix));
}

function slotPrefixAt(index) {
  return state.slots?.[index]?.prefix || "";
}

function isSlotFreeForNewFile(prefix) {
  return Boolean(prefix && !state.files.has(prefix) && !photoHasUsableContent(state.loadedPhotos.get(prefix)));
}

function nextFreeSlotPrefix(startPrefix, options = {}) {
  const start = slotIndex(startPrefix);
  if (start < 0) return "";
  const from = start + (options.after ? 1 : 0);
  for (let index = from; index < (state.slots || []).length; index += 1) {
    const prefix = slotPrefixAt(index);
    if (isSlotFreeForNewFile(prefix)) {
      return prefix;
    }
  }
  return "";
}

function warnNoFreeSlots(files, context = "") {
  const names = [...(files || [])]
    .map((file) => (typeof file === "string" ? file : file?.name || slotFileName(file)))
    .filter(Boolean);
  if (!names.length) return;
  const message =
    names.length === 1
      ? `Brak wolnego slotu dla pliku: ${names[0]}.`
      : `Brak wolnych slotow dla plikow: ${names.join(", ")}.`;
  formStatus.textContent = context ? `${message} ${context}` : message;
  window.alert(formStatus.textContent);
}

function fileListFromInput(files) {
  return Array.from(files || []).filter(Boolean);
}

function assignFilesFromSlot(startPrefix, files, options = {}) {
  const incoming = fileListFromInput(files);
  if (!incoming.length) return;
  const assigned = [];
  const unassigned = [];
  let searchPrefix = startPrefix;
  if (options.replaceStart && incoming.length === 1) {
    setSlotFile(startPrefix, incoming[0], { provisional: isProvisionalSlotPlacement(startPrefix) });
    renderSlot(startPrefix);
    formStatus.textContent = `Dodano plik do slotu ${startPrefix}.`;
    return;
  }
  for (const file of incoming) {
    const targetPrefix = nextFreeSlotPrefix(searchPrefix, { after: false });
    if (!targetPrefix) {
      unassigned.push(file);
      continue;
    }
    setSlotFile(targetPrefix, file, { provisional: isProvisionalSlotPlacement(targetPrefix) });
    assigned.push({ prefix: targetPrefix, file });
    searchPrefix = slotPrefixAt(slotIndex(targetPrefix) + 1) || targetPrefix;
  }
  for (const item of assigned) {
    renderSlot(item.prefix);
  }
  if (assigned.length) {
    const targetText = assigned.map((item) => item.prefix).join(", ");
    formStatus.textContent =
      assigned.length === 1
        ? `Dodano plik do slotu ${targetText}.`
        : `Dodano ${assigned.length} plikow do slotow: ${targetText}.`;
  }
  if (unassigned.length) {
    warnNoFreeSlots(unassigned);
  }
}

function applyDefaultSlotSource(prefix, photo) {
  const source = defaultSlotSource(photo);
  if (!state.userSelectedSlotSources.has(prefix)) {
    if (source) {
      state.slotSources.set(prefix, source);
    } else {
      state.slotSources.delete(prefix);
    }
  } else if (!selectedSlotSource(prefix, photo)) {
    if (source) {
      state.slotSources.set(prefix, source);
    } else {
      state.slotSources.delete(prefix);
    }
    state.userSelectedSlotSources.delete(prefix);
  }
}

function relocateProvisionalSlotFile(prefix) {
  const item = state.files.get(prefix);
  if (!item?.provisional) {
    return [];
  }
  const targetPrefix = nextFreeSlotPrefix(prefix, { after: true });
  if (!targetPrefix) {
    if (!item.placementBlocked) {
      warnNoFreeSlots([slotFileName(item)], `Slot ${prefix} ma juz dane.`);
    }
    item.placementBlocked = true;
    return [prefix];
  }
  const sourceFit = isSlotFit(prefix);
  state.files.delete(prefix);
  revokeFilePreviewUrl(prefix);
  item.prefix = targetPrefix;
  item.provisional = isProvisionalSlotPlacement(targetPrefix);
  item.placementBlocked = false;
  state.files.set(targetPrefix, item);
  state.slotFits.delete(prefix);
  state.slotFits.set(targetPrefix, sourceFit);
  formStatus.textContent = `Slot ${prefix} ma juz dane. Przeniesiono ${slotFileName(item)} do slotu ${targetPrefix}.`;
  return [prefix, targetPrefix];
}

function updateSlotPreview(prefix) {
  const card = slotGrid.querySelector(`[data-slot-prefix="${prefix}"]`);
  if (!card) {
    renderSlots();
    return;
  }
  const loadedPhoto = state.loadedPhotos.get(prefix);
  const selectedFile = state.files.get(prefix);
  const detail = card.querySelector(".slot-meta span");
  const preview = card.querySelector(".slot-preview");
  const previewImage = preview.querySelector("img");
  const empty = preview.querySelector(".slot-empty");
  const fitButton = card.querySelector(".slot-fit-button");
  card.dataset.activeSource = selectedSlotSource(prefix, loadedPhoto) || "";
  detail.textContent = selectedFile ? fileLabel(selectedFile) : slotStatusText(loadedPhoto, prefix);
  card.querySelectorAll(".slot-badge[data-source]").forEach((badge) => {
    const selected = selectedSlotSource(prefix, loadedPhoto) === badge.dataset.source;
    const loading =
      isPhotoSourceLoading(badge.dataset.source) ||
      (badge.dataset.source === "ftp" && state.ftpPreviewLoading.has(prefix));
    const titleBySource = {
      local: "Plik jest w folderze backendu",
      ftp: "Wpis dla slotu jest na FTP",
      sql: "Wpis dla slotu jest w SQL",
    };
    const sqlValue = String(loadedPhoto?.sql_value || "").trim();
    badge.classList.toggle("selected", selected);
    badge.classList.toggle("loading", loading);
    badge.setAttribute("aria-pressed", selected ? "true" : "false");
    if (loading) {
      badge.setAttribute("aria-busy", "true");
      badge.title = sourceLoadingTitle(badge.dataset.source);
    } else {
      badge.removeAttribute("aria-busy");
      const baseTitle =
        badge.dataset.source === "sql" && sqlValue
          ? "Kliknij, aby skopiowac link z SQL"
          : titleBySource[badge.dataset.source] || "";
      badge.title = selected ? `${baseTitle} (aktywny podglad)` : baseTitle;
    }
  });
  if (fitButton) {
    fitButton.classList.toggle("active", isSlotFit(prefix));
  }
  preview.classList.remove("has-image", "thumb-loading", "loaded-photo");
  preview.querySelector(".slot-upload-overlay")?.remove();
  previewImage.removeAttribute("src");
  empty.textContent = "Brak pliku";
  if (selectedFile) {
    if (isFileImageLike(selectedFile)) {
      renderSelectedFilePreview(prefix, selectedFile, preview, previewImage, empty);
    } else {
      empty.textContent = slotFileName(selectedFile);
    }
    renderSlotUploadOverlay(preview, selectedFile);
    return;
  }
  if (!loadedPhoto) return;
  preview.classList.add("loaded-photo");
  if (
    state.ftpPreviewLoading.has(prefix) &&
    !state.ftpPreviewBackgroundLoading.has(prefix) &&
    selectedSlotSource(prefix, loadedPhoto) === "ftp"
  ) {
    empty.textContent = "Pobieranie z FTP...";
    preview.classList.add("thumb-loading");
    return;
  }
  const thumb = thumbnailUrl(loadedPhoto, prefix);
  if (thumb && loadedPhoto.is_image) {
    preview.classList.add("thumb-loading");
    previewImage.addEventListener(
      "load",
      () => {
        preview.classList.remove("thumb-loading");
      },
      { once: true }
    );
    previewImage.addEventListener(
      "error",
      () => {
        preview.classList.remove("thumb-loading", "has-image");
        empty.textContent = "Podglad niedostepny";
      },
      { once: true }
    );
    previewImage.src = thumb;
    preview.classList.add("has-image");
    return;
  }
  empty.textContent =
    selectedSlotSource(prefix, loadedPhoto) === "ftp" && loadedPhoto.ftp_filename && !loadedPhoto.ftp_token
      ? "Kliknij FTP, aby pobrac podglad"
      : slotStatusText(loadedPhoto, prefix);
}

function createSlotNode(slot) {
    const node = slotTemplate.content.firstElementChild.cloneNode(true);
    const title = node.querySelector(".slot-meta strong");
    const detail = node.querySelector(".slot-meta span");
    const input = node.querySelector("input");
    const preview = node.querySelector(".slot-preview");
    const previewImage = node.querySelector("img");
    const empty = node.querySelector(".slot-empty");
    const meta = node.querySelector(".slot-meta");
    const loadedPhoto = state.loadedPhotos.get(slot.prefix);
    const selectedFile = state.files.get(slot.prefix);
    const overlay = document.createElement("div");
    const controls = document.createElement("div");
    const fitButton = document.createElement("button");
    const openButton = document.createElement("button");
    const clearButton = document.createElement("button");
    node.dataset.slotPrefix = slot.prefix;
    node.dataset.activeSource = selectedSlotSource(slot.prefix, loadedPhoto) || "";

    title.textContent = `${slot.prefix} - ${slot.label}`;
    detail.textContent = selectedFile ? fileLabel(selectedFile) : slotStatusText(loadedPhoto, slot.prefix);
    input.name = `slot_${slot.prefix}`;
    input.multiple = true;
    previewImage.draggable = false;
    previewImage.loading = "lazy";
    previewImage.decoding = "async";
    node.draggable = Boolean(selectedFile || loadedPhoto?.token || loadedPhoto?.ftp_token || loadedPhoto?.ftp_filename);
    renderSlotBadges(meta, loadedPhoto, selectedFile, slot.prefix);
    overlay.className = "slot-loading-overlay";
    overlay.innerHTML = `<span>${photoLoadingText()}</span><div class="progress-line"><i></i></div>`;
    if (state.photosLoading && !selectedFile && !loadedPhoto) {
      preview.appendChild(overlay);
    }
    controls.className = "slot-controls";
    fitButton.type = "button";
    fitButton.className = `slot-fit-button ${isSlotFit(slot.prefix) ? "active" : ""}`;
    fitButton.textContent = "FIT";
    fitButton.title = "Dopasuj zapis tego slotu do zawartosci obrazu";
    fitButton.addEventListener("click", (event) => {
      event.stopPropagation();
      state.slotFits.set(slot.prefix, !isSlotFit(slot.prefix));
      updateSlotPreview(slot.prefix);
    });
    openButton.type = "button";
    openButton.className = "slot-open-button";
    openButton.textContent = "Otworz";
    openButton.title = "Otworz oryginalny plik z tego slotu";
    openButton.addEventListener("click", (event) => {
      event.stopPropagation();
      openSlotFile(slot.prefix).catch((error) => {
        formStatus.textContent = error.message;
      });
    });
    clearButton.type = "button";
    clearButton.className = "slot-clear-button";
    clearButton.textContent = "Usun";
    clearButton.title = "Usun plik z tego slotu w formularzu";
    clearButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const hadSavedPhoto = Boolean(state.loadedPhotos.get(slot.prefix));
      clearSlotAssignment(slot.prefix);
      formStatus.textContent = hadSavedPhoto
        ? `Oznaczono slot ${slot.prefix} do usuniecia przy zapisie.`
        : `Wyczyszczono slot ${slot.prefix}.`;
      renderSlot(slot.prefix);
    });
    if (selectedFile || loadedPhoto) {
      const hasOpenableFile =
        Boolean(selectedFile) ||
        Boolean(selectedPhotoToken(loadedPhoto, slot.prefix)) ||
        Boolean(loadedPhoto?.ftp_filename);
      const hasFittablePreview =
        (selectedFile && isFileImageLike(selectedFile)) ||
        (loadedPhoto?.is_image && (selectedPhotoToken(loadedPhoto, slot.prefix) || loadedPhoto?.ftp_filename));
      if (hasFittablePreview) {
        controls.appendChild(fitButton);
      }
      if (hasOpenableFile) {
        controls.appendChild(openButton);
      }
      controls.appendChild(clearButton);
      meta.appendChild(controls);
    }

    if (selectedFile) {
      if (isFileImageLike(selectedFile)) {
        renderSelectedFilePreview(slot.prefix, selectedFile, preview, previewImage, empty);
      } else {
        empty.textContent = slotFileName(selectedFile);
      }
      renderSlotUploadOverlay(preview, selectedFile);
    } else if (loadedPhoto) {
      preview.classList.add("loaded-photo");
      const thumb = thumbnailUrl(loadedPhoto, slot.prefix);
      if (
        state.ftpPreviewLoading.has(slot.prefix) &&
        !state.ftpPreviewBackgroundLoading.has(slot.prefix) &&
        selectedSlotSource(slot.prefix, loadedPhoto) === "ftp"
      ) {
        preview.classList.add("thumb-loading");
        empty.textContent = "Pobieranie z FTP...";
      } else if (thumb && loadedPhoto.is_image) {
        preview.classList.add("thumb-loading");
        previewImage.addEventListener("load", () => {
          preview.classList.remove("thumb-loading");
        });
        previewImage.addEventListener("error", () => {
          preview.classList.remove("thumb-loading", "has-image");
          empty.textContent = "Podglad niedostepny";
        });
        previewImage.src = thumb;
        preview.classList.add("has-image");
      } else {
        empty.textContent =
          selectedSlotSource(slot.prefix, loadedPhoto) === "ftp" && loadedPhoto.ftp_filename && !loadedPhoto.ftp_token
            ? "Kliknij FTP, aby pobrac podglad"
            : slotStatusText(loadedPhoto, slot.prefix);
      }
    }

    node.addEventListener("dragstart", (event) => {
      const assignment = getSlotAssignment(slot.prefix);
      if (!assignment) {
        event.preventDefault();
        return;
      }
      state.draggedSlotPrefix = slot.prefix;
      event.dataTransfer.setData("application/x-picorg-slot", slot.prefix);
      event.dataTransfer.setData("text/plain", slot.prefix);
      event.dataTransfer.effectAllowed = "move";
    });
    node.addEventListener("dragover", (event) => {
      event.preventDefault();
      node.classList.add("drag-over");
      const sourcePrefix =
        event.dataTransfer.getData("application/x-picorg-slot") ||
        state.draggedSlotPrefix ||
        event.dataTransfer.getData("text/plain");
      event.dataTransfer.dropEffect = sourcePrefix ? "move" : "copy";
    });
    node.addEventListener("dragleave", () => {
      node.classList.remove("drag-over");
    });
    node.addEventListener("dragend", () => {
      state.draggedSlotPrefix = "";
      node.classList.remove("drag-over");
    });
    node.addEventListener("drop", (event) => {
      event.preventDefault();
      node.classList.remove("drag-over");
      const sourcePrefix =
        event.dataTransfer.getData("application/x-picorg-slot") ||
        state.draggedSlotPrefix ||
        event.dataTransfer.getData("text/plain");
      if (sourcePrefix && getSlotAssignment(sourcePrefix)) {
        state.draggedSlotPrefix = "";
        moveSlotContent(sourcePrefix, slot.prefix);
        return;
      }
      const files = fileListFromInput(event.dataTransfer.files);
      if (files.length) {
        state.draggedSlotPrefix = "";
        assignFilesFromSlot(slot.prefix, files);
      }
    });

    input.addEventListener("change", () => {
      const files = fileListFromInput(input.files);
      if (!files.length) {
        bumpSlotRevision(slot.prefix);
        revokeFilePreviewUrl(slot.prefix);
        state.files.delete(slot.prefix);
        renderSlot(slot.prefix);
        return;
      }
      assignFilesFromSlot(slot.prefix, files, { replaceStart: true });
      input.value = "";
    });

    return node;
}

function renderSlot(prefix) {
  const slot = (state.slots || []).find((item) => String(item.prefix) === String(prefix));
  const existing = slotGrid.querySelector(`[data-slot-prefix="${prefix}"]`);
  if (!slot || !existing) {
    renderSlots();
    return;
  }
  existing.replaceWith(createSlotNode(slot));
  updateSubmitButtonState();
}

function renderChangedSlots(prefixes, options = {}) {
  const uniquePrefixes = [...new Set([...(prefixes || [])].map((prefix) => String(prefix || "")).filter(Boolean))];
  for (const prefix of uniquePrefixes) {
    if (options.skipPendingUserEdits && slotHasPendingUserEdit(prefix)) continue;
    renderSlot(prefix);
  }
}

function renderSlotsExceptPendingUserEdits(prefixes = null) {
  const targetPrefixes = prefixes
    ? [...prefixes]
    : (state.slots || []).map((slot) => slot.prefix);
  renderChangedSlots(targetPrefixes, { skipPendingUserEdits: true });
}

function renderSlots(slots = state.slots) {
  slotGrid.textContent = "";
  state.slots = slots;
  slotCount.textContent = `${slots.length} pol`;

  for (const slot of slots) {
    slotGrid.appendChild(createSlotNode(slot));
  }
  updateSubmitButtonState();
}

function renderListTabs() {
  listTabs.textContent = "";
  for (const [key, label] of Object.entries(listLabels)) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${label} (${(state.lists[key] || []).length})`;
    button.classList.toggle("active", state.selectedList === key);
    button.addEventListener("click", () => {
      state.selectedList = key;
      state.listFilter = "";
      renderListEditor();
    });
    listTabs.appendChild(button);
  }
}

function normalizeListValue(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLocaleLowerCase("pl-PL");
}

function boundedEditDistance(a, b, maxDistance = 4) {
  if (Math.abs(a.length - b.length) > maxDistance) return maxDistance + 1;
  const previous = Array.from({ length: b.length + 1 }, (_, index) => index);
  const current = Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i += 1) {
    current[0] = i;
    let rowMin = current[0];
    for (let j = 1; j <= b.length; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
      rowMin = Math.min(rowMin, current[j]);
    }
    if (rowMin > maxDistance) return maxDistance + 1;
    for (let j = 0; j <= b.length; j += 1) previous[j] = current[j];
  }
  return previous[b.length];
}

function listMatch(value, query) {
  const normalized = normalizeListValue(value);
  const needle = normalizeListValue(query);
  if (!needle) {
    return { visible: true, rank: 9, distance: 0, className: "" };
  }
  if (normalized === needle) {
    return { visible: true, rank: 0, distance: 0, className: "exact-match" };
  }
  if (normalized.startsWith(needle)) {
    return { visible: true, rank: 1, distance: normalized.length - needle.length, className: "partial-match" };
  }
  if (normalized.includes(needle)) {
    return { visible: true, rank: 2, distance: normalized.length - needle.length, className: "partial-match" };
  }
  const maxDistance = needle.length <= 5 ? 2 : 4;
  const distance = boundedEditDistance(normalized, needle, maxDistance);
  if (distance <= maxDistance) {
    return { visible: true, rank: 3, distance, className: "similar-match" };
  }
  return { visible: false, rank: 99, distance: 99, className: "" };
}

function ensureListFilterInfo() {
  let info = document.querySelector("#listFilterInfo");
  if (!info) {
    info = document.createElement("div");
    info.id = "listFilterInfo";
    info.className = "list-filter-info";
    listAddForm.insertAdjacentElement("afterend", info);
  }
  return info;
}

function renderListEditor() {
  renderListTabs();
  listValues.textContent = "";
  listAddInput.value = state.listFilter;
  listAddInput.placeholder = `Nowa wartosc: ${listLabels[state.selectedList]}`;
  const info = ensureListFilterInfo();
  const query = state.listFilter;
  const values = state.lists[state.selectedList] || [];
  const rows = values
    .map((value, index) => ({ value, index, match: listMatch(value, query) }))
    .filter((item) => item.match.visible)
    .sort((left, right) => {
      if (!query) return left.index - right.index;
      return (
        left.match.rank - right.match.rank ||
        left.match.distance - right.match.distance ||
        left.value.localeCompare(right.value, "pl")
      );
    });
  const duplicate = Boolean(query) && values.some((value) => normalizeListValue(value) === normalizeListValue(query));
  if (query) {
    info.textContent = duplicate
      ? "Taka wartosc juz istnieje. Dodawanie duplikatu jest zablokowane."
      : `Pasujace wpisy: ${rows.length}. Enter doda nowa wartosc, jesli nie jest duplikatem.`;
    info.classList.toggle("duplicate", duplicate);
  } else {
    info.textContent = "";
    info.classList.remove("duplicate");
  }
  for (const { value, match } of rows) {
    const row = document.createElement("div");
    row.className = `list-value-row ${match.className}`;
    const text = document.createElement("span");
    const remove = document.createElement("button");
    text.textContent = value;
    if (match.rank === 3) {
      row.title = `Podobny wpis, roznica znakow: ${match.distance}`;
    }
    remove.type = "button";
    remove.className = "icon-button";
    remove.textContent = "X";
    remove.title = "Usun";
    remove.addEventListener("click", () => removeListValue(value));
    row.append(text, remove);
    listValues.appendChild(row);
  }
  if (!rows.length && query) {
    const empty = document.createElement("div");
    empty.className = "list-empty-filter";
    empty.textContent = "Brak podobnych wpisow.";
    listValues.appendChild(empty);
  }
}

function setBusy(isBusy, text = "") {
  if (submitButton) {
    submitButton.dataset.busy = isBusy ? "1" : "";
    submitButton.disabled = Boolean(isBusy);
  }
  formStatus.textContent = text;
  updateSubmitButtonState();
}

function stopProcessStatusTicker(text = "") {
  window.clearInterval(state.processStatusTimer);
  state.processStatusTimer = 0;
  state.processStatusStartedAt = 0;
  if (text) formStatus.textContent = text;
}

function startProcessStatusTicker(label, prefixes = new Set()) {
  stopProcessStatusTicker();
  const phaseTexts = [
    "backend zapisuje lokalne zmiany",
    "backend sprawdza brakujace zrodla",
    "backend synchronizuje FTP/SQL",
    "czekam na odpowiedz backendu",
  ];
  const changed = [...prefixes].filter(Boolean).sort();
  const slotText = changed.length ? ` Sloty: ${changed.join(", ")}.` : "";
  let step = 0;
  state.processStatusStartedAt = performance.now();
  const render = () => {
    const elapsed = Math.max(1, Math.round((performance.now() - state.processStatusStartedAt) / 1000));
    const phase = phaseTexts[Math.min(step, phaseTexts.length - 1)];
    formStatus.textContent = `${label}: ${phase} (${elapsed} s).${slotText}`;
    step += 1;
  };
  render();
  state.processStatusTimer = window.setInterval(render, 5000);
}

function clearResult() {
  resultMeta.textContent = "";
  resultOutput.className = "result-output empty-state";
  resultOutput.textContent = "Brak wykonanych operacji.";
}

function showError(error) {
  resultMeta.textContent = "";
  resultOutput.className = "result-output error-text";
  resultOutput.textContent = error.message || String(error);
}

function processingOperationLabel(operation) {
  const labels = {
    copy_preprocessed: "kopiowanie po obrobce",
    copy_without_processing: "kopiowanie bez obrobki",
    copy_document: "kopiowanie dokumentu",
    copy_unsupported_image: "kopiowanie formatu bez obrobki",
    copy_no_pillow: "kopiowanie bez Pillow",
    process_image: "resize/kompresja",
    same_target: "bez kopiowania",
  };
  return labels[operation] || operation || "plik";
}

function renderTimingDetails(timing, savedFiles = []) {
  const stages = timing?.stages || [];
  const files = savedFiles || [];
  if (!stages.length && !files.length) return null;
  const box = document.createElement("details");
  const summary = document.createElement("summary");
  const list = document.createElement("div");
  box.className = "timing-details";
  summary.textContent = `Czas operacji: ${formatDuration(timing?.total_ms)}`;
  list.className = "timing-list";
  for (const stage of stages) {
    const row = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("strong");
    label.textContent = stage.label || stage.key || "Etap";
    value.textContent = formatDuration(stage.elapsed_ms);
    row.append(label, value);
    list.appendChild(row);
  }
  if (files.length) {
    const section = document.createElement("div");
    section.className = "timing-section";
    section.textContent = "Pliki";
    list.appendChild(section);
  }
  for (const file of files) {
    const row = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("strong");
    const flags = [];
    if (file.preprocessed) flags.push("preprocessed");
    if (file.content_fit) flags.push("FIT");
    const sizes =
      file.source_size_bytes || file.size_bytes
        ? ` (${formatFileSize(file.source_size_bytes)} -> ${formatFileSize(file.size_bytes)})`
        : "";
    const suffix = flags.length ? `, ${flags.join(", ")}` : "";
    const operation = processingOperationLabel(file.operation);
    label.textContent = `${file.prefix || "Slot"} - ${operation}${suffix}${sizes}`;
    value.textContent = formatDuration(file.elapsed_ms);
    row.append(label, value);
    list.appendChild(row);
  }
  box.append(summary, list);
  return box;
}

function showResult(payload) {
  resultOutput.className = "result-output";
  resultOutput.textContent = "";
  resultMeta.textContent = `${payload.saved_files.length} zapisanych`;
  const dir = document.createElement("p");
  dir.className = "ok-text";
  dir.textContent = payload.output_dir;
  resultOutput.appendChild(dir);
  if (payload.entry && payload.entry.product_id) {
    productForm.elements.product_id.value = payload.entry.product_id;
  }
  if (!productForm.elements.ean.value && payload.ean && payload.ean !== "BRAK-EAN") {
    productForm.elements.ean.value = payload.ean;
  }
  const list = document.createElement("ul");
  list.className = "result-list";
  for (const file of payload.saved_files || []) {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    const path = document.createElement("span");
    name.textContent = `${file.prefix} - ${file.filename}`;
    path.textContent = file.path;
    item.append(name, path);
    list.appendChild(item);
  }
  if ((payload.saved_files || []).length) {
    resultOutput.appendChild(list);
  } else {
    const noFiles = document.createElement("p");
    noFiles.className = "ok-text";
    noFiles.textContent = "Nie dodano nowych plikow; zapisano pozostale zmiany.";
    resultOutput.appendChild(noFiles);
  }
  if (payload.ftp?.enabled) {
    const ftp = document.createElement("p");
    ftp.className = payload.ftp.error ? "error-text" : "ok-text";
    ftp.textContent = payload.ftp.error
      ? `FTP: blad - ${payload.ftp.error}`
      : `FTP: wyslano ${payload.ftp.uploaded || 0}, usunieto ${
          payload.ftp.deleted || 0
        }. Czas: ${formatDuration(payload.ftp.elapsed_ms)}.`;
    resultOutput.appendChild(ftp);
  }
  if (
    payload.local_delete?.deleted ||
    payload.local_delete?.skipped ||
    (payload.local_delete?.errors || []).length
  ) {
    const deletions = document.createElement("p");
    const deleteErrors = payload.local_delete?.errors || [];
    deletions.className = deleteErrors.length ? "error-text" : "ok-text";
    deletions.textContent = deleteErrors.length
      ? `Usuwanie lokalne: ${payload.local_delete.deleted || 0}, pominieto: ${
          payload.local_delete.skipped || 0
        }, bledy: ${deleteErrors.join("; ")}`
      : `Usunieto lokalnie: ${payload.local_delete.deleted || 0}, pominieto: ${
          payload.local_delete.skipped || 0
        }`;
    resultOutput.appendChild(deletions);
  }
  if (payload.sql?.enabled) {
    const sql = document.createElement("p");
    sql.className = payload.sql.error ? "error-text" : "ok-text";
    sql.textContent = payload.sql.error
      ? `SQL: blad - ${payload.sql.error}`
      : payload.sql.skipped
        ? `SQL: pominieto - ${payload.sql.reason || "brak wiersza do aktualizacji"}`
        : `SQL: aktualizacje ${payload.sql.updated || 0}, czyszczenia ${
            payload.sql.cleared || 0
          }. Czas: ${formatDuration(payload.sql.elapsed_ms)}.`;
    resultOutput.appendChild(sql);
  }
  if (payload.show_timing_details) {
    const timing = renderTimingDetails(payload.timing, payload.saved_files || []);
    if (timing) resultOutput.appendChild(timing);
  }
}

function entryFromHistoryGroup(group) {
  for (const item of group.items || []) {
    if (item.details?.entry) return item.details.entry;
  }
  return {};
}

function entryField(entry, ...keys) {
  for (const key of keys) {
    const value = entry?.[key];
    if (value) return value;
  }
  return "";
}

function historyEntryLabel(entry) {
  const colors = [
    entryField(entry, "KOLOR1", "color1"),
    entryField(entry, "KOLOR2", "color2"),
    entryField(entry, "KOLOR3", "color3"),
  ]
    .filter(Boolean)
    .join(" / ");
  return [
    entryField(entry, "NAZWA", "name") ? `Nazwa: ${entryField(entry, "NAZWA", "name")}` : "",
    entryField(entry, "TYP", "type_name") ? `Typ: ${entryField(entry, "TYP", "type_name")}` : "",
    entryField(entry, "MODEL", "model") ? `Model: ${entryField(entry, "MODEL", "model")}` : "",
    colors ? `Kolory: ${colors}` : "",
    entryField(entry, "DODATKI", "extra") ? `Dodatek: ${entryField(entry, "DODATKI", "extra")}` : "",
  ]
    .filter(Boolean)
    .join(" | ");
}

function renderHistoryDetails(group) {
  historyDetailTitle.textContent = `Historia EAN ${group.ean}`;
  historyDetailOutput.textContent = "";
  for (const item of group.items || []) {
    const row = document.createElement("article");
    const meta = document.createElement("div");
    const summary = document.createElement("strong");
    const details = document.createElement("span");
    row.className = "history-item";
    meta.className = "history-meta";
    meta.textContent = `${item.time || ""} | ${item.user || ""}`;
    summary.textContent = item.summary || item.action || "Zmiana";
    const saved = item.details?.saved_files?.length || 0;
    const deleted = item.details?.deleted_slots?.length || 0;
    const ftp = item.details?.ftp;
    const sql = item.details?.sql;
    details.textContent = [
      historyEntryLabel(item.details?.entry) || "",
      saved ? `zapisane pliki: ${saved}` : "",
      deleted ? `usuniete sloty: ${deleted}` : "",
      item.details?.local_delete?.deleted ? `usunieto lokalnie: ${item.details.local_delete.deleted}` : "",
      ftp?.enabled ? `FTP wyslano/usunieto: ${ftp.uploaded || 0}/${ftp.deleted || 0}${ftp.error ? `, blad: ${ftp.error}` : ""}` : "",
      sql?.enabled ? `SQL aktualizacje/czyszczenia: ${sql.updated || 0}/${sql.cleared || 0}${sql.error ? `, blad: ${sql.error}` : ""}` : "",
    ]
      .filter(Boolean)
      .join(" | ");
    row.append(meta, summary, details);
    historyDetailOutput.appendChild(row);
  }
  document.querySelector("#historyDetailModal").classList.add("active");
}

function renderHistory(payload) {
  state.history = payload;
  const selectedUser = historyUserFilter.value;
  historyUserFilter.textContent = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "Wszyscy uzytkownicy";
  historyUserFilter.appendChild(all);
  for (const user of payload.users || []) {
    const option = document.createElement("option");
    option.value = user;
    option.textContent = user;
    option.selected = user === selectedUser;
    historyUserFilter.appendChild(option);
  }
  historyOutput.textContent = "";
  const groups = payload.groups || [];
  if (!groups.length) {
    historyOutput.className = "history-output empty-state";
    historyOutput.textContent = "Brak historii dla wybranego filtra.";
    return;
  }
  historyOutput.className = "history-output";
  for (const group of groups) {
    const entry = entryFromHistoryGroup(group);
    const row = document.createElement("button");
    const title = document.createElement("strong");
    const fields = document.createElement("span");
    const meta = document.createElement("small");
    row.type = "button";
    row.className = "history-summary-row";
    title.textContent = `EAN ${group.ean}`;
    const readableFields = historyEntryLabel(entry);
    fields.textContent = readableFields || "Brak danych pol tekstowych";
    meta.textContent = `${(group.items || []).length} zmian | ostatnio: ${group.items?.[0]?.time || ""}`;
    row.append(title, fields, meta);
    row.addEventListener("click", () => renderHistoryDetails(group));
    historyOutput.appendChild(row);
  }
}

async function loadHistory() {
  const params = new URLSearchParams({ user: historyUserFilter.value || "", limit: "300" });
  const payload = await requestJson(`/api/history?${params.toString()}`);
  renderHistory(payload);
}

function logReadStorageKey() {
  const username = state.currentUser?.username || "anonymous";
  return `picorg-log-read-${username}`;
}

function readLogMarker() {
  try {
    return JSON.parse(localStorage.getItem(logReadStorageKey()) || "{}");
  } catch (_error) {
    return {};
  }
}

function writeLogMarker(summary = {}) {
  const marker = {
    critical: summary.latest_critical_id || "",
    warning: summary.latest_warning_id || "",
  };
  localStorage.setItem(logReadStorageKey(), JSON.stringify(marker));
  return marker;
}

function unreadLogSeverity(summary = {}) {
  const marker = readLogMarker();
  if (summary.latest_critical_id && summary.latest_critical_id !== marker.critical) {
    return "critical";
  }
  if (summary.latest_warning_id && summary.latest_warning_id !== marker.warning) {
    return "warning";
  }
  return "";
}

function updateLogAlert(summary = {}, { initialize = false } = {}) {
  if (!logsButton || !state.isAdmin) {
    logsButton?.classList.remove("log-alert-critical", "log-alert-warning");
    return;
  }
  if (initialize && !localStorage.getItem(logReadStorageKey())) {
    writeLogMarker(summary);
  }
  const severity = unreadLogSeverity(summary);
  logsButton.classList.toggle("log-alert-critical", severity === "critical");
  logsButton.classList.toggle("log-alert-warning", severity === "warning");
  if (severity === "critical") {
    logsButton.title = "Nowy krytyczny blad w logach.";
  } else if (severity === "warning") {
    logsButton.title = "Nowe ostrzezenie w logach.";
  } else {
    logsButton.title = "";
  }
}

function markLogsRead(payload = {}) {
  writeLogMarker(payload.summary || {});
  updateLogAlert(payload.summary || {});
}

function logSeverityLabel(severity = "info") {
  if (severity === "critical") return "Krytyczny";
  if (severity === "warning") return "Ostrzezenie";
  return "Info";
}

function renderLogEvent(event) {
  const block = document.createElement("article");
  const meta = document.createElement("div");
  const title = document.createElement("strong");
  const source = document.createElement("span");
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  const lines = document.createElement("pre");
  const severity = event.severity || "info";
  block.className = `log-event log-event-${severity}`;
  meta.className = "log-event-meta";
  meta.textContent = [event.time || "", logSeverityLabel(severity)].filter(Boolean).join(" | ");
  title.textContent = event.summary || "Zdarzenie";
  source.textContent = event.path || "";
  summary.textContent = "Szczegoly";
  lines.className = "log-lines";
  lines.textContent = (event.lines || []).join("\n");
  details.append(summary, lines);
  block.append(meta, title, source, details);
  return block;
}

function renderLogs(payload) {
  state.logs = payload;
  logsOutput.textContent = "";
  const logs = payload.logs || [];
  const hasEvents = logs.some((log) => (log.events || []).length);
  if (!hasEvents) {
    logsOutput.className = "logs-output empty-state";
    logsOutput.textContent = "Brak zdarzen w logach systemowych.";
    return;
  }
  logsOutput.className = "logs-output";
  for (const log of logs) {
    const category = document.createElement("section");
    const heading = document.createElement("div");
    const title = document.createElement("strong");
    const path = document.createElement("span");
    const events = log.events || [];
    category.className = "log-category";
    heading.className = "log-category-heading";
    title.textContent = `${log.label || log.key || "Log"} (${events.length})`;
    path.textContent = log.path || "";
    heading.append(title, path);
    category.appendChild(heading);
    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "Brak zdarzen w tej kategorii.";
      category.appendChild(empty);
    } else {
      for (const event of events) {
        category.appendChild(renderLogEvent(event));
      }
    }
    logsOutput.appendChild(category);
  }
}

async function loadLogs({ markRead = true } = {}) {
  const payload = await requestJson("/api/logs?limit=400");
  updateLogAlert(payload.summary || {});
  renderLogs(payload);
  if (markRead) {
    markLogsRead(payload);
  }
}

async function pollLogStatus({ initialize = false } = {}) {
  if (!state.isAdmin) {
    updateLogAlert({});
    return;
  }
  const payload = await requestJson("/api/logs?limit=120");
  updateLogAlert(payload.summary || {}, { initialize });
}

function openLogsClearModal() {
  if (!logsClearPassword || !logsClearStatus) {
    return;
  }
  logsClearStatus.textContent = "";
  logsClearPassword.value = "";
  document.querySelector("#logsClearModal")?.classList.add("active");
  window.setTimeout(() => logsClearPassword?.focus(), 0);
}

function closeLogsClearModal() {
  if (!logsClearPassword || !logsClearStatus) {
    return;
  }
  logsClearPassword.value = "";
  logsClearStatus.textContent = "";
  document.querySelector("#logsClearModal")?.classList.remove("active");
}

async function clearLogs(password) {
  if (!password) {
    return;
  }
  if (logsClearStatus) {
    logsClearStatus.textContent = "Czyszczenie...";
  }
  const payload = await requestJson("/api/logs/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  renderLogs(payload);
  markLogsRead(payload);
  if ((payload.clear_errors || []).length) {
    if (logsClearStatus) {
      logsClearStatus.textContent = `Nie wyczyszczono wszystkich logow: ${(payload.clear_errors || []).join(
        "; "
      )}`;
    }
    return;
  }
  closeLogsClearModal();
}

function formPayload() {
  return {
    product_id: productForm.elements.product_id.value,
    name: productForm.elements.name.value,
    type_name: productForm.elements.type_name.value,
    model: productForm.elements.model.value,
    color1: productForm.elements.color1.value,
    color2: productForm.elements.color2.value,
    color3: productForm.elements.color3.value,
    extra: productForm.elements.extra.value,
    ean: productForm.elements.ean.value,
  };
}

function normalizedIdentityValue(value) {
  return String(value || "").trim().toUpperCase();
}

function productEntryLabel(entry = {}) {
  const colors = [entry.color1, entry.color2, entry.color3].filter(Boolean).join(" / ");
  const parts = [entry.name, entry.type_name, entry.model, colors, entry.extra].filter(Boolean);
  const suffix = entry.ean ? `EAN ${entry.ean}` : entry.product_id || "";
  return parts.join(" | ") + (suffix ? ` - ${suffix}` : "");
}

function entryFromProcessPayload(payload = {}, fallback = {}) {
  const result = payload.entry || {};
  const raw = result.entry || {};
  const entry = {
    product_id: result.product_id || raw.PRODUCT_ID || fallback.product_id || "",
    ean: raw.EAN || fallback.ean || payload.ean || "",
    name: raw.NAZWA || fallback.name || "",
    type_name: raw.TYP || fallback.type_name || "",
    model: raw.MODEL || fallback.model || "",
    color1: raw.KOLOR1 || fallback.color1 || "",
    color2: raw.KOLOR2 || fallback.color2 || "",
    color3: raw.KOLOR3 || fallback.color3 || "",
    extra: raw.DODATKI || fallback.extra || "",
  };
  entry.label = productEntryLabel(entry);
  return entry;
}

function upsertProductEntry(entry = {}) {
  if (!entry.product_id && !entry.ean) return;
  const productId = normalizedIdentityValue(entry.product_id);
  const ean = normalizedIdentityValue(entry.ean);
  const entries = [...(state.entries || [])];
  const index = entries.findIndex((item) => {
    const itemProductId = normalizedIdentityValue(item.product_id);
    const itemEan = normalizedIdentityValue(item.ean);
    return (productId && itemProductId === productId) || (ean && itemEan === ean);
  });
  if (index >= 0) {
    entries[index] = { ...entries[index], ...entry, label: entry.label || entries[index].label };
  } else {
    entries.unshift(entry);
  }
  state.entries = entries;
  renderEntrySelect();
}

function productFieldsChangedSinceLoad() {
  if (!state.loadedEntryOriginal) {
    return false;
  }
  const current = formPayload();
  return trackedProductFields.some(
    (fieldName) =>
      normalizedIdentityValue(current[fieldName]) !==
      normalizedIdentityValue(state.loadedEntryOriginal[fieldName])
  );
}

function hasProductDraftData() {
  const current = formPayload();
  return trackedProductFields.some((fieldName) => String(current[fieldName] || "").trim());
}

function hasPendingSlotChanges() {
  if (state.files.size || state.deletedSlots.size) {
    return true;
  }
  for (const [prefix, photo] of state.loadedPhotos.entries()) {
    if (photo?.dirty) {
      return true;
    }
  }
  return false;
}

function slotHasPendingUserEdit(prefix) {
  return Boolean(
    state.files.has(prefix) ||
      state.deletedSlots.has(prefix) ||
      state.loadedPhotos.get(prefix)?.dirty
  );
}

function pendingChangedSlotPrefixes() {
  const prefixes = new Set();
  for (const prefix of state.files.keys()) prefixes.add(prefix);
  for (const prefix of state.deletedSlots.keys()) prefixes.add(prefix);
  for (const [prefix, photo] of state.loadedPhotos.entries()) {
    if (photo?.dirty) {
      prefixes.add(prefix);
    }
  }
  return prefixes;
}

function clearSavedSlotMarkers(prefixes) {
  for (const prefix of prefixes || []) {
    const photo = state.loadedPhotos.get(prefix);
    if (photo?.dirty) {
      const clean = { ...photo };
      delete clean.dirty;
      state.loadedPhotos.set(prefix, clean);
    }
    state.deletedSlots.delete(prefix);
    state.files.delete(prefix);
    state.userSelectedSlotSources.delete(prefix);
  }
}

function hasPendingUserChanges() {
  return (
    hasPendingSlotChanges() ||
    productFieldsChangedSinceLoad() ||
    (!state.loadedEntryOriginal && hasProductDraftData())
  );
}

function updateSubmitButtonState() {
  if (!submitButton || submitButton.dataset.busy === "1") {
    return;
  }
  const pendingUploads = activeSlotUploads();
  if (pendingUploads.length) {
    submitButton.disabled = true;
    submitButton.textContent = `Wysylanie ${pendingUploads.length}`;
    submitButton.title = "Poczekaj, az nowe pliki trafia do cache backendu.";
    submitButton.setAttribute("aria-label", submitButton.textContent);
    return;
  }
  const failedUploads = failedSlotUploads();
  if (failedUploads.length) {
    submitButton.disabled = true;
    submitButton.textContent = "Upload nieudany";
    submitButton.title = "Popraw slot z nieudanym uploadem albo wybierz plik ponownie.";
    submitButton.setAttribute("aria-label", submitButton.textContent);
    return;
  }
  submitButton.disabled = false;
  const hasChanges = hasPendingUserChanges();
  submitButton.textContent = hasChanges ? "Aktualizuj" : "Synchronizuj";
  submitButton.title = hasChanges
    ? "Zapisuje zmiany w danych i slotach oraz aktualizuje lokalne pliki, FTP i SQL."
    : "Pobiera brakujace zdjecia z FTP i uzupelnia lokalne pliki.";
  submitButton.setAttribute("aria-label", submitButton.textContent);
}

function pageExitWarningText() {
  const reasons = [];
  if (hasPendingUserChanges()) reasons.push("sa niezapisane zmiany");
  if (activeSlotUploads().length) reasons.push("trwa wysylanie plikow");
  if (state.photosLoading) reasons.push("trwa wczytywanie danych");
  if (submitButton?.dataset.busy === "1") reasons.push("trwa zapisywanie");
  const detail = reasons.length ? ` (${reasons.join(", ")})` : "";
  return `Opuscic strone${detail}?`;
}

function shouldConfirmPageExit() {
  if (state.navigationGuardBypass) return false;
  return Boolean(
    hasPendingUserChanges() ||
      activeSlotUploads().length ||
      state.photosLoading ||
      submitButton?.dataset.busy === "1"
  );
}

function confirmPageExit() {
  if (!shouldConfirmPageExit()) return true;
  return window.confirm(pageExitWarningText());
}

function continueBrowserBackNavigation() {
  state.navigationGuardBypass = true;
  window.history.back();
  window.setTimeout(() => {
    state.navigationGuardBypass = false;
    if (!window.history.state?.picorgLeaveGuard) {
      window.history.pushState({ picorgLeaveGuard: true }, "", window.location.href);
    }
  }, 600);
}

function setupPageExitGuards() {
  window.addEventListener("beforeunload", (event) => {
    if (!shouldConfirmPageExit()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  if (!window.history?.pushState) {
    return;
  }
  window.history.replaceState({ ...(window.history.state || {}), picorgBase: true }, "", window.location.href);
  window.history.pushState({ picorgLeaveGuard: true }, "", window.location.href);
  window.addEventListener("popstate", () => {
    if (state.navigationGuardBypass) return;
    if (!confirmPageExit()) {
      window.history.pushState({ picorgLeaveGuard: true }, "", window.location.href);
      return;
    }
    continueBrowserBackNavigation();
  });
}

function mergePhotoRecord(existing = {}, incoming = {}) {
  const merged = { ...existing, ...incoming };
  for (const key of ["local", "ftp", "sql", "is_image", "sql_checked"]) {
    merged[key] = Boolean(existing[key] || incoming[key]);
  }
  for (const key of [
    "filename",
    "path",
    "token",
    "url",
    "thumb_url",
    "file_version",
    "ftp_filename",
    "ftp_path",
    "ftp_token",
    "ftp_url",
    "ftp_thumb_url",
    "ftp_file_version",
    "sql_value",
  ]) {
    if (incoming[key]) {
      merged[key] = incoming[key];
    } else if (existing[key]) {
      merged[key] = existing[key];
    } else {
      merged[key] = "";
    }
  }
  if (incoming.sql_checked) {
    merged.sql = Boolean(incoming.sql);
    merged.sql_checked = true;
    merged.sql_value = incoming.sql_value || "";
  }
  merged.prefix = incoming.prefix || existing.prefix || "";
  const cachedFtp = state.ftpPreviewCache.get(
    ftpPreviewCacheKey(merged, formValue("ean") || state.loadedEntryOriginal?.ean || "")
  );
  if (cachedFtp) {
    return applyCachedFtpPreview(merged, merged.prefix, cachedFtp);
  }
  return merged;
}

function photoLoadingText() {
  const loading = [];
  for (const [source, status] of state.photoSourceStatus.entries()) {
    if (status === "pending" || status === "loading") {
      loading.push(photoSourceLabels[source] || source);
    }
  }
  return loading.length ? `Wczytywanie: ${loading.join(", ")}` : "Wczytywanie";
}

function photoStatusSummary() {
  const done = [];
  const loading = [];
  const failed = [];
  for (const [source, status] of state.photoSourceStatus.entries()) {
    if (status === "done") done.push(photoSourceLabels[source] || source);
    if (status === "pending" || status === "loading") loading.push(photoSourceLabels[source] || source);
    if (status === "failed") failed.push(photoSourceLabels[source] || source);
  }
  const parts = [];
  if (done.length) parts.push(`gotowe: ${done.join(", ")}`);
  if (loading.length) parts.push(`trwa: ${loading.join(", ")}`);
  if (failed.length) parts.push(`blad: ${failed.join(", ")}`);
  return parts.join(" | ");
}

function setPhotoSourceStatus(source, status, requestId) {
  if (requestId !== state.photoLoadRequestId) return;
  state.photoSourceStatus.set(source, status);
  const summary = photoStatusSummary();
  formStatus.textContent = summary || photoLoadingText();
}

function applyPhotoPayload(photos = [], options = {}) {
  const changedPrefixes = new Set();
  const allowedPrefixes = options.prefixes instanceof Set ? options.prefixes : null;
  for (const photo of photos) {
    if (!photo?.prefix) continue;
    if (allowedPrefixes && !allowedPrefixes.has(photo.prefix)) continue;
    if (!options.force && state.files.has(photo.prefix)) {
      const existing = state.loadedPhotos.get(photo.prefix) || {};
      const merged = mergePhotoRecord(existing, photo);
      state.loadedPhotos.set(photo.prefix, merged);
      applyDefaultSlotSource(photo.prefix, merged);
      if (photoHasUsableContent(photo)) {
        for (const changedPrefix of relocateProvisionalSlotFile(photo.prefix)) {
          changedPrefixes.add(changedPrefix);
        }
      }
      continue;
    }
    if (!options.force && slotHasPendingUserEdit(photo.prefix)) continue;
    const existing = state.loadedPhotos.get(photo.prefix) || {};
    const merged = mergePhotoRecord(existing, photo);
    if (options.clearDirty) {
      delete merged.dirty;
    }
    state.loadedPhotos.set(photo.prefix, merged);
    applyDefaultSlotSource(photo.prefix, merged);
    changedPrefixes.add(photo.prefix);
  }
  if (changedPrefixes.size) {
    renderChangedSlots(changedPrefixes);
    scheduleBackgroundFtpPreviewLoad(undefined, 1500);
  }
  return changedPrefixes;
}

function photoRequestTimeoutMs(source) {
  if (source === "ftp") return 15000;
  if (source === "all") return 25000;
  return 20000;
}

async function requestEntryPhotos(entry, source, prefixes = null, options = {}) {
  const params = new URLSearchParams({ source });
  if (prefixes && prefixes.size) {
    params.set("prefixes", [...prefixes].join(","));
  }
  return requestJson(`/api/entries/photos?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
    timeoutMs: Number(options.timeoutMs || photoRequestTimeoutMs(source)),
  });
}

function backgroundFtpLookupKey(fields = formPayload()) {
  const ean = normalizedIdentityValue(fields.ean);
  if (!state.ftpEnabled || !/^\d{13}$/.test(ean)) return "";
  for (const fieldName of ["name", "type_name", "model", "color1"]) {
    if (!String(fields[fieldName] || "").trim()) return "";
  }
  return [
    ean,
    normalizedIdentityValue(fields.name),
    normalizedIdentityValue(fields.type_name),
    normalizedIdentityValue(fields.model),
    normalizedIdentityValue(fields.color1),
    normalizedIdentityValue(fields.color2),
    normalizedIdentityValue(fields.color3),
    normalizedIdentityValue(fields.extra),
  ].join("|");
}

function clearStaleBackgroundFtpPhotos(activeKey) {
  let changed = false;
  for (const [prefix, photo] of Array.from(state.loadedPhotos.entries())) {
    if (!photo?.background_ftp_key || photo.background_ftp_key === activeKey) continue;
    if (slotHasPendingUserEdit(prefix)) continue;
    state.loadedPhotos.delete(prefix);
    state.slotSources.delete(prefix);
    state.userSelectedSlotSources.delete(prefix);
    changed = true;
    renderSlot(prefix);
  }
  if (changed) updateSubmitButtonState();
}

async function loadBackgroundFtpPhotosForCurrentForm() {
  const entry = formPayload();
  const key = backgroundFtpLookupKey(entry);
  if (!key) {
    state.backgroundFtpLookupKey = "";
    clearStaleBackgroundFtpPhotos("");
    return;
  }
  clearStaleBackgroundFtpPhotos(key);
  if (state.backgroundFtpLookupKey === key) return;
  state.backgroundFtpLookupKey = key;
  const requestId = state.backgroundFtpLookupRequestId + 1;
  state.backgroundFtpLookupRequestId = requestId;
  try {
    const payload = await requestEntryPhotos(entry, "ftp", null, { timeoutMs: 15000 });
    if (state.backgroundFtpLookupRequestId !== requestId) return;
    if (backgroundFtpLookupKey() !== key) return;
    const photos = (payload.photos || []).map((photo) => ({
      ...photo,
      background_ftp_key: key,
    }));
    applyPhotoPayload(photos, { force: false });
    if (photos.length) {
      formStatus.textContent = `Znaleziono zdjecia FTP: ${photos.length}.`;
    }
    updateSubmitButtonState();
  } catch (error) {
    if (state.backgroundFtpLookupRequestId === requestId && showTimingDetails()) {
      formStatus.textContent = `Nie udalo sie sprawdzic FTP w tle: ${error.message}`;
    }
  }
}

function scheduleBackgroundFtpLookup(delay = 900) {
  window.clearTimeout(state.backgroundFtpLookupTimer);
  state.backgroundFtpLookupTimer = window.setTimeout(() => {
    loadBackgroundFtpPhotosForCurrentForm().catch(() => {});
  }, delay);
}

function clearSelectedFiles() {
  for (const prefix of Array.from(state.filePreviewUrls.keys())) {
    revokeFilePreviewUrl(prefix);
  }
  state.files.clear();
}

async function loadPhotosForEntry(entry, options = {}) {
  const started = performance.now();
  const progressive = options.progressive !== false;
  const targetPrefixes = new Set((options.prefixes || []).map((prefix) => String(prefix || "").trim()).filter(Boolean));
  const partial = targetPrefixes.size > 0;
  const requestId = state.photoLoadRequestId + 1;
  state.photoLoadRequestId = requestId;
  state.photosLoading = true;
  const collectedPrefixes = new Set();
  if (!partial) {
    state.loadedPhotos.clear();
    state.deletedSlots.clear();
    state.slotSources.clear();
    state.userSelectedSlotSources.clear();
    state.ftpPreviewLoading.clear();
    state.ftpPreviewBackgroundLoading.clear();
    state.photoSourcesLoaded.clear();
    state.backgroundFtpLookupKey = "";
    state.backgroundFtpLookupRequestId += 1;
    window.clearTimeout(state.backgroundFtpLookupTimer);
  } else {
    for (const prefix of targetPrefixes) {
      state.ftpPreviewLoading.delete(prefix);
      state.ftpPreviewBackgroundLoading.delete(prefix);
      state.userSelectedSlotSources.delete(prefix);
    }
  }
  window.clearTimeout(state.backgroundFtpPreviewTimer);
  const sources = progressive ? ["local", "sql", "ftp"] : ["all"];
  state.photoSourceStatus.clear();
  for (const source of sources) {
    state.photoSourceStatus.set(source, "pending");
  }
  formStatus.textContent = photoLoadingText();
  if (!partial) {
    renderSlotsExceptPendingUserEdits();
  }
  const tasks = sources.map(async (source) => {
    setPhotoSourceStatus(source, "loading", requestId);
    try {
      const payload = await requestEntryPhotos(entry, source, partial ? targetPrefixes : null);
      if (state.photoLoadRequestId === requestId) {
        setPhotoSourceStatus(source, "done", requestId);
        state.photoSourcesLoaded.add(payload.source || source);
        const payloadPhotos = partial
          ? (payload.photos || []).filter((photo) => targetPrefixes.has(photo?.prefix))
          : payload.photos || [];
        for (const photo of payloadPhotos) {
          if (photo?.prefix) collectedPrefixes.add(photo.prefix);
        }
        applyPhotoPayload(payloadPhotos, {
          prefixes: partial ? targetPrefixes : null,
          force: Boolean(options.force),
          clearDirty: Boolean(options.clearDirty),
        });
        if ((payload.source || source) === "ftp" || (payload.source || source) === "all") {
          scheduleBackgroundFtpPreviewLoad(requestId, 1200);
        }
        updateSubmitButtonState();
      }
      return payload;
    } catch (error) {
      setPhotoSourceStatus(source, "failed", requestId);
      throw error;
    }
  });
  try {
    const settled = await Promise.allSettled(tasks);
    if (state.photoLoadRequestId !== requestId) return;
    const failures = settled.filter((item) => item.status === "rejected");
    if (failures.length && failures.length === settled.length) {
      throw failures[0].reason;
    }
    if (failures.length) {
      formStatus.textContent = "Czesc zrodel podgladu nie odpowiedziala.";
    } else {
      formStatus.textContent = photoStatusSummary() || "Wczytano podglady.";
    }
    state.lastLookupMs = performance.now() - started;
  } finally {
    if (state.photoLoadRequestId !== requestId) return;
    state.photosLoading = false;
    state.photoSourceStatus.clear();
    if (partial) {
      for (const prefix of targetPrefixes) {
        if (!collectedPrefixes.has(prefix) && !slotHasPendingUserEdit(prefix)) {
          state.loadedPhotos.delete(prefix);
          state.slotSources.delete(prefix);
          state.userSelectedSlotSources.delete(prefix);
          state.slotFits.delete(prefix);
          bumpSlotRevision(prefix);
        }
      }
    }
    updateRuntimeMetrics();
    renderSlotsExceptPendingUserEdits(partial ? targetPrefixes : null);
    scheduleBackgroundFtpPreviewLoad(requestId, 1500);
  }
}

function fillForm(entry, options = {}) {
  state.suppressAutoSearch = true;
  state.loadedEntryOriginal = { ...entry };
  state.slotFits.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
  state.userSelectedSlotSources.clear();
  state.ftpPreviewLoading.clear();
  state.ftpPreviewBackgroundLoading.clear();
  state.photoSourcesLoaded.clear();
  state.backgroundFtpLookupKey = "";
  state.backgroundFtpLookupRequestId += 1;
  window.clearTimeout(state.backgroundFtpLookupTimer);
  productForm.elements.product_id.value = entry.product_id || "";
  productForm.elements.name.value = entry.name || "";
  productForm.elements.type_name.value = entry.type_name || "";
  productForm.elements.model.value = entry.model || "";
  productForm.elements.color1.value = entry.color1 || "";
  productForm.elements.color2.value = entry.color2 || "";
  productForm.elements.color3.value = entry.color3 || "";
  productForm.elements.extra.value = entry.extra || "";
  productForm.elements.ean.value = entry.ean || "";
  formStatus.textContent = entry.product_id ? `Wczytano ${entry.product_id}` : "Wczytano wpis";
  updateFieldWarnings();
  setTimeout(() => {
    state.suppressAutoSearch = false;
  }, 200);
  if (options.loadPhotos) {
    loadPhotosForEntry(entry).catch((error) => {
      formStatus.textContent = `Wpis wczytany, ale zdjecia nie: ${error.message}`;
    });
  }
}

async function refreshData() {
  const payload = await requestJson("/api/data");
  state.lists = payload.lists || {};
  state.entries = payload.entries || [];
  state.fileIndex = payload.file_index || state.fileIndex;
  state.ftpEnabled = payload.ftp_enabled !== false;
  state.colorFieldLabels = payload.color_field_labels || state.colorFieldLabels || {};
  renderDatalists();
  applyProductFieldLabels();
  renderEntrySelect();
  renderListEditor();
  updateRuntimeMetrics();
}

async function loadBootstrap(options = {}) {
  const payload = await requestJson("/api/bootstrap", options);
  state.defaultSlotFit = Boolean(payload.auto_content_fit);
  state.processing = payload.processing || state.processing || {};
  state.ftpEnabled = payload.ftp_enabled !== false;
  if (versionInfo) {
    versionInfo.textContent = payload.version ? `Wersja ${payload.version}` : "";
  }
  serverInfo.textContent = payload.processed_dir;
  logoutButton.style.display = payload.auth_enabled ? "" : "none";
  state.currentUser = payload.current_user || null;
  updateAdminUi();
  pollLogStatus({ initialize: true }).catch(() => {});
  state.lists = payload.lists || {};
  state.entries = payload.entries || [];
  state.fileIndex = payload.file_index || null;
  state.ftpEnabled = payload.ftp_enabled !== false;
  state.colorFieldLabels = payload.color_field_labels || {};
  state.processing = payload.processing || state.processing || {};
  renderDatalists();
  applyProductFieldLabels();
  renderEntrySelect();
  renderSlots(payload.slots || []);
  renderListEditor();
  updateRuntimeMetrics();
}

async function refreshFileIndexStatus() {
  const payload = await requestJson("/api/file-index/status");
  state.fileIndex = payload;
  updateRuntimeMetrics();
}

async function searchByEan() {
  const ean = productForm.elements.ean.value.trim();
  if (!ean) {
    formStatus.textContent = "Wpisz EAN do wyszukania.";
    return;
  }
  const payload = await requestJson(`/api/entries/search?ean=${encodeURIComponent(ean)}`);
  renderEntrySelect(payload.entries || []);
  if (payload.entries && payload.entries.length === 1) {
    fillForm(payload.entries[0], { loadPhotos: true });
  } else {
    renderEntryModal(payload.entries || []);
    formStatus.textContent = `${(payload.entries || []).length} dopasowan po EAN.`;
  }
}

async function searchByProduct({ automatic = false } = {}) {
  const fields = formPayload();
  const params = new URLSearchParams({
    name: fields.name,
    type_name: fields.type_name,
    model: fields.model,
  });
  const payload = await requestJson(`/api/entries/search?${params.toString()}`);
  renderEntrySelect(payload.entries || []);
  if (payload.entries && payload.entries.length > 0) {
    renderEntryModal(payload.entries);
  }
  if (!automatic) {
    formStatus.textContent = `${(payload.entries || []).length} dopasowan produktu.`;
  }
}

let autoSearchTimer = null;
function scheduleProductAutoSearch() {
  if (state.suppressAutoSearch) {
    return;
  }
  clearTimeout(autoSearchTimer);
  autoSearchTimer = setTimeout(() => {
    const fields = formPayload();
    const key = `${fields.name}|${fields.type_name}|${fields.model}`.toUpperCase();
    if (!fields.name || !fields.type_name || !fields.model || key === state.lastAutoSearchKey) {
      return;
    }
    state.lastAutoSearchKey = key;
    searchByProduct({ automatic: true }).catch(() => {});
  }, 500);
}

async function addListValue(event) {
  event.preventDefault();
  const value = listAddInput.value.trim();
  if (!value) {
    listStatus.textContent = "Wpisz wartosc.";
    return;
  }
  const exists = (state.lists[state.selectedList] || []).some(
    (item) => normalizeListValue(item) === normalizeListValue(value)
  );
  if (exists) {
    listStatus.textContent = "Taka wartosc juz istnieje na liscie.";
    state.listFilter = value;
    renderListEditor();
    return;
  }
  const payload = await requestJson(`/api/lists/${state.selectedList}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  state.lists = payload.lists || {};
  state.entries = payload.entries || state.entries;
  state.listFilter = "";
  renderDatalists();
  renderListEditor();
  listStatus.textContent = "Dodano.";
}

async function removeListValue(value) {
  const listLabel = listLabels[state.selectedList] || state.selectedList;
  if (!window.confirm(`Usunac "${value}" z listy ${listLabel}?`)) {
    return;
  }
  let payload;
  try {
    payload = await requestJson(`/api/lists/${state.selectedList}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
  } catch (error) {
    const detail = error.detail || {};
    if (error.status === 409 && Array.isArray(detail.used_by)) {
      renderListUsageModal(detail.value || value, detail.used_by);
      listStatus.textContent = error.message;
      return;
    }
    throw error;
  }
  state.lists = payload.lists || {};
  state.entries = payload.entries || state.entries;
  renderDatalists();
  renderListEditor();
  listStatus.textContent = "Usunieto.";
}

function inputField(name, label, value = "", attrs = {}) {
  const wrapper = document.createElement("label");
  const input = document.createElement(attrs.textarea ? "textarea" : "input");
  wrapper.textContent = label;
  input.name = name;
  if (attrs.type) input.type = attrs.type;
  if (attrs.className) wrapper.className = attrs.className;
  if (attrs.min !== undefined) input.min = attrs.min;
  if (attrs.max !== undefined) input.max = attrs.max;
  if (attrs.step !== undefined) input.step = attrs.step;
  if (attrs.placeholder !== undefined) input.placeholder = attrs.placeholder;
  if (attrs.checked !== undefined) input.checked = Boolean(attrs.checked);
  if (attrs.type === "checkbox") {
    input.value = "1";
  } else {
    input.value = value || "";
  }
  wrapper.appendChild(input);
  if (attrs.description) {
    const small = document.createElement("small");
    small.textContent = attrs.description;
    wrapper.appendChild(small);
  }
  return wrapper;
}

function checkField(name, label, checked = false, description = "") {
  const wrapper = document.createElement("div");
  const input = document.createElement("input");
  const text = document.createElement("div");
  const title = document.createElement("strong");
  wrapper.className = "check-row";
  input.type = "checkbox";
  input.name = name;
  input.checked = Boolean(checked);
  input.setAttribute("aria-label", label);
  title.textContent = label;
  text.appendChild(title);
  if (description) {
    const small = document.createElement("small");
    small.textContent = description;
    text.appendChild(small);
  }
  wrapper.append(input, text);
  return wrapper;
}

function credentialField(name, label, isSet = false, attrs = {}) {
  const field = document.createElement("label");
  const title = document.createElement("span");
  const row = document.createElement("span");
  const input = document.createElement("input");
  const originalType = attrs.type || "text";
  field.className = attrs.className ? `credential-field ${attrs.className}` : "credential-field";
  title.textContent = label;
  row.className = "credential-actions";
  input.name = name;
  input.type = originalType;
  input.placeholder = isSet ? "Zapisane - wpisz nowe, zeby zmienic" : "Nie ustawiono";
  row.appendChild(input);
  if (attrs.secretPath && isSet) {
    const reveal = document.createElement("button");
    reveal.type = "button";
    reveal.className = "secondary-button";
    reveal.textContent = "Pokaz zapisane";
    reveal.title = "Wczytuje zapisana wartosc tylko do tego pola.";
    reveal.addEventListener("click", () => {
      toggleCredentialReveal(input, reveal, attrs.secretPath, originalType);
    });
    row.appendChild(reveal);
  }
  field.append(title, row);
  return field;
}

function secretValueByPath(payload, path) {
  let value = payload;
  for (const part of String(path || "").split(".")) {
    if (!part) continue;
    value = value?.[part];
  }
  return value === undefined || value === null ? "" : String(value);
}

async function loadSettingsSecrets() {
  if (!state.settingsSecrets) {
    state.settingsSecrets = await requestJson("/api/settings/secrets", { timeoutMs: 10000 });
  }
  return state.settingsSecrets;
}

async function toggleCredentialReveal(input, button, secretPath, originalType) {
  if (input.dataset.secretVisible === "1") {
    input.value = "";
    input.type = originalType;
    input.dataset.secretVisible = "";
    button.textContent = "Pokaz zapisane";
    return;
  }
  const previousLabel = button.textContent;
  button.disabled = true;
  button.textContent = "Wczytywanie...";
  try {
    const payload = await loadSettingsSecrets();
    const value = secretValueByPath(payload, secretPath);
    if (!value) {
      settingsStatus.textContent = "Brak zapisanej wartosci albo nie mozna jej odczytac aktualnym APP_SECRET.";
      button.textContent = previousLabel;
      return;
    }
    input.value = value;
    if (originalType === "password") {
      input.type = "text";
    }
    input.dataset.secretVisible = "1";
    button.textContent = "Ukryj";
    settingsStatus.textContent = "Wczytano zapisana wartosc do pola. Zapisz tylko wtedy, gdy chcesz ja utrwalic.";
  } catch (error) {
    settingsStatus.textContent = error.message || "Nie udalo sie wczytac zapisanej wartosci.";
    button.textContent = previousLabel;
  } finally {
    button.disabled = false;
  }
}

function selectField(name, label, value, choices) {
  const wrapper = document.createElement("label");
  const select = document.createElement("select");
  wrapper.textContent = label;
  select.name = name;
  for (const [choiceValue, choiceLabel] of choices) {
    const option = document.createElement("option");
    option.value = choiceValue;
    option.textContent = choiceLabel;
    option.selected = choiceValue === value;
    select.appendChild(option);
  }
  wrapper.appendChild(select);
  return wrapper;
}

function actionRow(...buttons) {
  const actions = document.createElement("div");
  actions.className = "settings-actions";
  actions.append(...buttons);
  return actions;
}

function formatDiagnosticResult(target, payload) {
  if (target === "local" && Array.isArray(payload.checks)) {
    const failed = payload.checks.filter((item) => !item.read || !item.write);
    if (!failed.length) {
      return "Foldery lokalne: odczyt i zapis dzialaja.";
    }
    return failed
      .map((item) => `${item.key}: ${item.error || "brak odczytu lub zapisu"} (${item.path})`)
      .join(" | ");
  }
  return payload.message || (payload.ok ? "Test zakonczony powodzeniem." : "Test nie powiodl sie.");
}

function diagnosticButton(target, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Testowanie...";
    try {
      const payload = await requestJson(`/api/diagnostics/${target}`, { method: "POST" });
      settingsStatus.textContent = formatDiagnosticResult(target, payload);
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function fileIndexRefreshButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Odswiez indeks";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Uruchamiam indeksowanie...";
    try {
      const payload = await requestJson("/api/file-index/refresh", { method: "POST" });
      state.fileIndex = payload;
      updateRuntimeMetrics();
      settingsStatus.textContent = payload.label || "Indeksowanie uruchomione.";
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function ensureSqlColumnsDatalist() {
  let datalist = document.querySelector("#sqlColumnsList");
  if (!datalist) {
    datalist = document.createElement("datalist");
    datalist.id = "sqlColumnsList";
    document.body.appendChild(datalist);
  }
  datalist.textContent = "";
  for (const column of state.settings?.sql_available_columns || []) {
    const option = document.createElement("option");
    option.value = column;
    datalist.appendChild(option);
  }
}

function settingsSaveButton(form, buildPayload) {
  const actions = document.createElement("div");
  actions.className = "settings-actions";
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Zapisz ustawienia";
  actions.appendChild(button);
  form.appendChild(actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const previousBaseDir = state.settings?.base_dir || "";
    button.disabled = true;
    settingsStatus.textContent = "Zapisywanie...";
    try {
      state.settingsSecrets = null;
      state.settings = await requestJson("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(new FormData(form))),
        timeoutMs: 60000,
      });
      state.currentUser = state.settings.current_user || state.currentUser;
      state.defaultSlotFit = Boolean(state.settings.auto_content_fit);
      state.ftpEnabled = state.settings.ftp?.enabled !== false;
      state.processing = state.settings.processing || state.processing || {};
      state.colorFieldLabels = state.settings.color_field_labels || state.colorFieldLabels || {};
      updateAdminUi();
      if (Array.isArray(state.settings.slots)) {
        renderSlots(state.settings.slots);
      }
      applyProductFieldLabels();
      let saveMessage = "Zapisano.";
      if (previousBaseDir && state.settings.base_dir !== previousBaseDir) {
        try {
          await loadBootstrap({ timeoutMs: 60000 });
          saveMessage = `Zapisano. Aktywny katalog bazowy: ${state.settings.base_dir}`;
        } catch (error) {
          saveMessage =
            `Zapisano katalog bazowy: ${state.settings.base_dir}. ` +
            `Nie udalo sie odswiezyc danych po zapisie: ${error.message || error}`;
        }
      }
      renderSettings();
      settingsStatus.textContent = saveMessage;
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie zapisac ustawien.";
    } finally {
      button.disabled = false;
    }
  });
}

function renderSettingsApp() {
  const s = state.settings;
  const form = document.createElement("form");
  form.className = "settings-form";
  const configNote = document.createElement("p");
  configNote.className = "settings-note wide-field";
  configNote.textContent =
    `Panel webowy uzywa tej samej lokalizacji, config.json i APP_SECRET co lokalna aplikacja uruchomiona na backendzie. local_settings.json: ${
      s.local_settings_path || "nieznany"
    }`;
  const runtimeWarning = document.createElement("p");
  runtimeWarning.className = "settings-note wide-field";
  runtimeWarning.textContent = s.runtime_warning ? `Ostrzezenie runtime: ${s.runtime_warning}` : "";
  const versionNote = document.createElement("p");
  versionNote.className = "settings-note wide-field";
  versionNote.textContent = `Wersja programu: ${s.version || "dev"}`;
  const colorGroup = document.createElement("div");
  colorGroup.className = "settings-field-group wide-field";
  const colorTitle = document.createElement("h2");
  colorTitle.textContent = "Nazwy pol kolorow";
  const colorGrid = document.createElement("div");
  colorGrid.className = "settings-form nested-grid";
  colorGrid.append(
    inputField("color1", "Kolor 1", s.color_field_labels?.color1 || ""),
    inputField("color2", "Kolor 2", s.color_field_labels?.color2 || ""),
    inputField("color3", "Kolor 3", s.color_field_labels?.color3 || "")
  );
  colorGroup.append(colorTitle, colorGrid);
  const secretGroup = document.createElement("div");
  const secretTitle = document.createElement("h2");
  const secretHint = document.createElement("p");
  const secretGrid = document.createElement("div");
  secretGroup.className = "settings-field-group wide-field";
  secretTitle.textContent = "Sekret aplikacji";
  secretHint.className = "settings-note";
  secretHint.textContent =
    "APP_SECRET sluzy do odczytu zaszyfrowanych hasel z config.json. " +
    "Przy podpinaniu istniejacego katalogu wpisz sekret uzyty przy jego konfiguracji; puste pole niczego nie zmienia.";
  secretGrid.className = "settings-form nested-grid";
  secretGrid.append(
    credentialField("app_secret", "APP_SECRET", s.app_secret_set, {
      type: "password",
      secretPath: "app_secret",
    })
  );
  secretGroup.append(secretTitle, secretHint, secretGrid);
  form.append(
    versionNote,
    configNote,
    runtimeWarning,
    inputField("base_dir", "Katalog bazowy", s.base_dir, {
      placeholder: "np. C:\\PicOrgFTP-SQL albo \\\\SERWER\\Udzial\\PicOrgFTP-SQL",
      description:
        "Folder, w ktorym backend trzyma config.json, lists.xlsx i katalog zdjec. " +
        "Dla uslugi Windows najlepiej uzywac pelnej sciezki lokalnej albo UNC; dyski mapowane typu Z:\\ moga nie byc widoczne.",
    }),
    secretGroup,
    checkField(
      "local_file_index",
      "Indeks plikow lokalnych",
      s.local_file_index,
      "Backend sprawdza lokalne pliki przy wczytywaniu statusow slotow."
    ),
    colorGroup,
    actionRow(diagnosticButton("local", "Test folderow backendu"), fileIndexRefreshButton())
  );
  settingsSaveButton(form, (data) => ({
    app: {
      base_dir: data.get("base_dir"),
      app_secret: data.get("app_secret"),
      local_file_index: data.has("local_file_index"),
      color_field_labels: {
        color1: data.get("color1"),
        color2: data.get("color2"),
        color3: data.get("color3"),
      },
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsProcessing() {
  const p = state.settings.processing || {};
  const formats = state.settings.processing_formats?.length
    ? state.settings.processing_formats
    : ["JPG", "PNG", "WEBP", "BMP", "GIF", "TIFF"];
  const form = document.createElement("form");
  form.className = "settings-form";
  const note = document.createElement("p");
  note.className = "settings-note wide-field";
  note.textContent =
    "Te ustawienia sa stosowane przy zapisie z panelu webowego. FIT w slocie nadal moze byc wlaczany osobno dla pojedynczego zdjecia.";
  form.append(
    note,
    checkField(
      "auto_content_fit",
      "FIT domyslnie dla kazdego slotu",
      state.settings.auto_content_fit,
      "Nowe i wczytane sloty startuja z wlaczonym FIT, ale pojedynczy slot nadal mozna przelaczyc."
    ),
    selectField(
      "upload_processing_mode",
      "Kiedy przetwarzac obrazy",
      p.upload_processing_mode || "save",
      [
        ["save", "Host przy zapisie"],
        ["host", "Host przy uploadzie do cache"],
        ["client", "Klient przed uploadem"],
      ]
    ),
    checkField(
      "show_timing_details",
      "Pokazuj szczegolowe czasy operacji",
      p.show_timing_details,
      "Po zapisie pokazuje czytelny rozklad czasu dla lokalnych plikow, FTP, SQL i cache."
    ),
    checkField(
      "resize_enabled",
      "Zmniejszanie obrazu",
      p.resize_enabled,
      "Najdluzszy bok obrazu zostanie ograniczony do podanej liczby pikseli."
    ),
    inputField("max_dim", "Maksymalny bok (px)", p.max_dim || 2000, {
      type: "number",
      min: 64,
      max: 20000,
    }),
    checkField(
      "compress_enabled",
      "Kompresja JPG/WEBP",
      p.compress_enabled,
      "Uzywa podanej jakosci przy zapisie stratnych formatow."
    ),
    inputField("compress_quality", "Jakosc (%)", p.compress_quality || 85, {
      type: "number",
      min: 1,
      max: 100,
    }),
    checkField(
      "max_size_enabled",
      "Limit rozmiaru pliku",
      p.max_size_enabled,
      "Dla JPG/WEBP jakosc jest obnizana stopniowo, az plik miesci sie w limicie."
    ),
    inputField("max_file_kb", "Maksymalny rozmiar (KB)", p.max_file_kb || 500, {
      type: "number",
      min: 1,
      max: 102400,
    }),
    checkField(
      "convert_enabled",
      "Konwersja formatu obrazow",
      p.convert_enabled,
      "Obrazy sa zapisywane w wybranym formacie zamiast w formacie zrodlowym."
    ),
    selectField(
      "target_format",
      "Format docelowy",
      p.target_format || "PNG",
      formats.map((format) => [format, format])
    )
  );
  settingsSaveButton(form, (data) => ({
    app: {
      auto_content_fit: data.has("auto_content_fit"),
    },
    processing: {
      resize_enabled: data.has("resize_enabled"),
      max_dim: data.get("max_dim"),
      compress_enabled: data.has("compress_enabled"),
      compress_quality: data.get("compress_quality"),
      max_size_enabled: data.has("max_size_enabled"),
      max_file_kb: data.get("max_file_kb"),
      convert_enabled: data.has("convert_enabled"),
      target_format: data.get("target_format"),
      upload_processing_mode: data.get("upload_processing_mode"),
      show_timing_details: data.has("show_timing_details"),
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsFtp() {
  const ftp = state.settings.ftp;
  const form = document.createElement("form");
  form.className = "settings-form";
  form.append(
    checkField(
      "enabled",
      "Aktualizacja FTP",
      ftp.enabled,
      "Po zapisie backend bedzie wysylal przetworzone pliki na FTP."
    ),
    inputField("host", "Host", ftp.host),
    inputField("port", "Port", ftp.port, { type: "number" }),
    inputField("path", "Sciezka", ftp.path),
    credentialField("user", "Uzytkownik", ftp.user_set, { secretPath: "ftp.user" }),
    credentialField("password", "Haslo", ftp.password_set, {
      type: "password",
      secretPath: "ftp.password",
    }),
    actionRow(diagnosticButton("ftp", "Test FTP"))
  );
  settingsSaveButton(form, (data) => ({
    ftp: {
      enabled: data.has("enabled"),
      host: data.get("host"),
      port: data.get("port"),
      path: data.get("path"),
      user: data.get("user"),
      password: data.get("password"),
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsSql() {
  const db = state.settings.database;
  const form = document.createElement("form");
  form.className = "settings-form";
  form.append(
    selectField("type", "Typ bazy", db.type, [["mysql", "MySQL"], ["mssql", "MS SQL"]]),
    checkField(
      "sql_update_enabled",
      "Aktualizacja SQL",
      db.sql_update_enabled,
      "Backend bedzie aktualizowal pola SQL przypisane w zakladce Sloty."
    ),
    inputField("query", "Zapytanie SQL", db.query, { textarea: true, className: "wide-field" }),
    inputField("mssql_server", "MS SQL server", db.mssql.server),
    inputField("mssql_database", "MS SQL database", db.mssql.database),
    credentialField("mssql_user", "MS SQL user", db.mssql.user_set, {
      secretPath: "database.mssql.user",
    }),
    credentialField("mssql_password", "MS SQL haslo", db.mssql.password_set, {
      type: "password",
      secretPath: "database.mssql.password",
    }),
    inputField("mysql_server", "MySQL server", db.mysql.server),
    inputField("mysql_database", "MySQL database", db.mysql.database),
    credentialField("mysql_user", "MySQL user", db.mysql.user_set, {
      secretPath: "database.mysql.user",
    }),
    credentialField("mysql_password", "MySQL haslo", db.mysql.password_set, {
      type: "password",
      secretPath: "database.mysql.password",
    }),
    actionRow(diagnosticButton("sql", "Test SQL"))
  );
  settingsSaveButton(form, (data) => ({
    database: {
      type: data.get("type"),
      sql_update_enabled: data.has("sql_update_enabled"),
      query: data.get("query"),
      mssql: {
        server: data.get("mssql_server"),
        database: data.get("mssql_database"),
        user: data.get("mssql_user"),
        password: data.get("mssql_password"),
      },
      mysql: {
        server: data.get("mysql_server"),
        database: data.get("mysql_database"),
        user: data.get("mysql_user"),
        password: data.get("mysql_password"),
      },
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsSlots() {
  ensureSqlColumnsDatalist();
  const form = document.createElement("form");
  form.className = "settings-form";
  const note = document.createElement("p");
  note.className = "settings-note wide-field";
  note.textContent =
    "Nazwa w web jest tylko etykieta slotu. ID trafia do EAN_ID, nazwa w pliku jest zapisywana literalnie po usunieciu znakow niedozwolonych, a pole SQL sluzy do aktualizacji bazy.";
  const list = document.createElement("div");
  const addButton = document.createElement("button");
  list.className = "slot-settings-list";
  const nextPrefix = () => {
    const used = [...list.querySelectorAll('[name="prefix"]')]
      .map((input) => parseInt(input.value, 10))
      .filter((value) => Number.isFinite(value));
    const next = Math.max(0, ...used) + 1;
    return String(next).padStart(2, "0");
  };
  const addSlotRow = (slot = {}) => {
    const row = document.createElement("div");
    const remove = document.createElement("button");
    row.className = "slot-settings-row";
    row.dataset.filenameLabelExplicit = slot.filename_label_explicit ? "1" : "0";
    row.dataset.originalLabel = slot.label || "";
    row.dataset.originalFilenameLabel = slot.filename_label || slot.label || "";
    const column = inputField("sql_column", "Pole SQL", slot.sql_column || "");
    column.querySelector("input").setAttribute("list", "sqlColumnsList");
    remove.type = "button";
    remove.className = "secondary-button";
    remove.textContent = "Usun";
    remove.addEventListener("click", () => row.remove());
    row.append(
      inputField("label", "Nazwa w web", slot.label),
      inputField("prefix", "ID", slot.prefix),
      inputField("filename_label", "Nazwa w pliku", slot.filename_label || slot.label),
      column,
      remove
    );
    list.appendChild(row);
  };
  for (const slot of state.settings.slots || []) {
    addSlotRow(slot);
  }
  addButton.type = "button";
  addButton.className = "secondary-button";
  addButton.textContent = "Dodaj slot";
  addButton.addEventListener("click", () => {
    const prefix = nextPrefix();
    addSlotRow({
      prefix,
      label: `Slot ${prefix}`,
      filename_label: `Slot ${prefix}`,
      filename_label_explicit: true,
      sql_column: "",
    });
  });
  form.append(note, list, actionRow(addButton));
  settingsSaveButton(form, () => {
    const slots = [...form.querySelectorAll(".slot-settings-row")].map((row) => {
      const label = row.querySelector('[name="label"]').value;
      const filenameLabel = row.querySelector('[name="filename_label"]').value;
      const wasExplicit = row.dataset.filenameLabelExplicit === "1";
      const originalLabel = row.dataset.originalLabel || "";
      const originalFilenameLabel = row.dataset.originalFilenameLabel || "";
      const unchangedLegacyFilename =
        !wasExplicit && label === originalLabel && filenameLabel === originalFilenameLabel;
      return {
        prefix: row.querySelector('[name="prefix"]').value,
        label,
        filename_label: unchangedLegacyFilename ? "" : filenameLabel,
        sql_column: row.querySelector('[name="sql_column"]').value,
      };
    });
    return { slots };
  });
  settingsOutput.appendChild(form);
}

function renderSettingsUsers() {
  const wrapper = document.createElement("div");
  wrapper.className = "settings-form";
  const addForm = document.createElement("form");
  addForm.className = "user-add-form wide-field";
  const input = document.createElement("input");
  const password = document.createElement("input");
  const role = document.createElement("select");
  const button = document.createElement("button");
  input.name = "username";
  input.placeholder = "Nowy uzytkownik";
  password.name = "password";
  password.type = "password";
  password.placeholder = "Haslo";
  for (const value of ["user", "admin"]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    role.appendChild(option);
  }
  button.textContent = "Dodaj";
  addForm.append(input, password, role, button);
  addForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = await requestJson("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: input.value, password: password.value, role: role.value }),
    });
    state.settings.users = payload.users;
    state.currentUser = payload.current_user || state.currentUser;
    updateAdminUi();
    input.value = "";
    password.value = "";
    renderSettings();
  });
  const list = document.createElement("div");
  list.className = "user-list";
  for (const user of state.settings.users || []) {
    const row = document.createElement("div");
    row.className = "user-row";
    const name = document.createElement("strong");
    const role = document.createElement("select");
    const enabled = document.createElement("input");
    const enabledWrap = document.createElement("div");
    const enabledText = document.createElement("div");
    const enabledTitle = document.createElement("strong");
    const enabledDescription = document.createElement("small");
    const passwordInput = document.createElement("input");
    const save = document.createElement("button");
    const isCurrentUser =
      state.currentUser &&
      String(state.currentUser.username || "").toLowerCase() === String(user.username || "").toLowerCase();
    name.textContent = user.username;
    for (const value of ["user", "admin"]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = user.role === value;
      role.appendChild(option);
    }
    enabled.type = "checkbox";
    enabled.checked = Boolean(user.enabled);
    enabled.disabled = Boolean(isCurrentUser);
    enabled.setAttribute("aria-label", `Konto aktywne: ${user.username}`);
    enabledTitle.textContent = "Konto aktywne";
    enabledDescription.textContent = isCurrentUser
      ? "Nie mozna wylaczyc konta aktualnej sesji."
      : "Wylaczenie blokuje logowanie tego uzytkownika.";
    enabledText.append(enabledTitle, enabledDescription);
    enabledWrap.className = "check-row compact-check";
    enabledWrap.append(enabled, enabledText);
    passwordInput.type = "password";
    passwordInput.placeholder = user.has_password ? "Nowe haslo opcjonalnie" : "Ustaw haslo";
    save.type = "button";
    save.textContent = "Zapisz";
    save.addEventListener("click", async () => {
      const payload = { enabled: enabled.checked, role: role.value };
      if (passwordInput.value) {
        payload.password = passwordInput.value;
      }
      const response = await requestJson(`/api/users/${encodeURIComponent(user.username)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.settings.users = response.users;
      state.currentUser = response.current_user || state.currentUser;
      updateAdminUi();
      renderSettings();
    });
    row.append(name, role, passwordInput, enabledWrap, save);
    list.appendChild(row);
  }
  wrapper.append(addForm, list);
  settingsOutput.appendChild(wrapper);
}

function renderSettings() {
  if (!state.settings) {
    return;
  }
  settingsOutput.textContent = "";
  document.querySelectorAll(".settings-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.settingsTab === state.activeSettingsTab);
  });
  settingsStatus.textContent = state.settings.windows_admin
    ? "Proces backendu ma uprawnienia administratora Windows. Rola web admin jest niezalezna."
    : "Proces backendu dziala bez uprawnien administratora Windows. Rola web admin jest niezalezna.";
  if (state.activeSettingsTab === "app") renderSettingsApp();
  if (state.activeSettingsTab === "processing") renderSettingsProcessing();
  if (state.activeSettingsTab === "ftp") renderSettingsFtp();
  if (state.activeSettingsTab === "sql") renderSettingsSql();
  if (state.activeSettingsTab === "slots") renderSettingsSlots();
  if (state.activeSettingsTab === "users") renderSettingsUsers();
}

async function loadSettings() {
  state.settings = await requestJson("/api/settings");
  state.settingsSecrets = null;
  state.currentUser = state.settings.current_user || state.currentUser;
  state.defaultSlotFit = Boolean(state.settings.auto_content_fit);
  state.ftpEnabled = state.settings.ftp?.enabled !== false;
  state.processing = state.settings.processing || state.processing || {};
  state.colorFieldLabels = state.settings.color_field_labels || state.colorFieldLabels || {};
  updateAdminUi();
  applyProductFieldLabels();
  renderSettings();
}

document.querySelectorAll("[data-modal]").forEach((button) => {
  button.addEventListener("click", () => openModal(button.dataset.modal));
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", closeModals);
});

document.querySelectorAll("[data-close-web-images]").forEach((button) => {
  button.addEventListener("click", closeWebImagesModal);
});

document.querySelectorAll("[data-close-history-detail]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#historyDetailModal")?.classList.remove("active");
  });
});

document.querySelectorAll("[data-close-logs-clear]").forEach((button) => {
  button.addEventListener("click", closeLogsClearModal);
});

themeToggleButton?.addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  applyTheme();
});

document.querySelectorAll(".settings-tab").forEach((button) => {
  button.addEventListener("click", () => {
    state.activeSettingsTab = button.dataset.settingsTab;
    renderSettings();
  });
});

historyUserFilter?.addEventListener("change", () => {
  loadHistory().catch((error) => {
    historyOutput.textContent = error.message;
  });
});

historyRefreshButton?.addEventListener("click", () => {
  loadHistory().catch((error) => {
    historyOutput.textContent = error.message;
  });
});

logsRefreshButton?.addEventListener("click", () => {
  loadLogs().catch((error) => {
    logsOutput.textContent = error.message;
  });
});

logsClearButton?.addEventListener("click", () => {
  openLogsClearModal();
});

logsClearForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  clearLogs(logsClearPassword.value).catch((error) => {
    if (logsClearStatus) {
      logsClearStatus.textContent = error.message;
    }
  });
});

entrySelect.addEventListener("change", () => {
  const option = entrySelect.selectedOptions[0];
  if (!option || !option.dataset.entry) return;
  fillForm(JSON.parse(option.dataset.entry), { loadPhotos: true });
});

for (const name of ["name", "type_name", "model"]) {
  productForm.elements[name].addEventListener("input", scheduleProductAutoSearch);
}

for (const name of trackedProductFields) {
  productForm.elements[name]?.addEventListener("input", () => scheduleBackgroundFtpLookup());
}

for (const name of Object.keys(fieldListKey)) {
  productForm.elements[name]?.addEventListener("change", () => {
    promptAddProductFieldToList(name).catch((error) => {
      formStatus.textContent = error.message;
    });
  });
}

productForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearResult();
  try {
    ensureSlotUploadsReady();
    setBusy(true, "Sprawdzanie list...");
    await ensureProductListValues();
    const identityChanged = productFieldsChangedSinceLoad();
    const updateMode = hasPendingUserChanges();
    setBusy(
      true,
      updateMode
        ? identityChanged
          ? "Aktualizowanie i przenoszenie istniejacych zdjec..."
          : "Aktualizowanie..."
        : "Synchronizowanie brakujacych danych..."
    );
    const changedPrefixes = pendingChangedSlotPrefixes();
    const data = new FormData(productForm);
    for (const slot of state.slots || []) {
      data.delete(`slot_${slot.prefix}`);
    }
    for (const [prefix, item] of state.files.entries()) {
      const token = slotFileToken(item);
      if (token) {
        data.set(`existing_slot_${prefix}`, token);
        data.set(`existing_slot_name_${prefix}`, slotFileName(item));
        if (item.preprocessed) {
          data.set(`existing_slot_preprocessed_${prefix}`, "1");
        }
      } else {
        const file = slotFileObject(item);
        if (!file) {
          throw new Error(`Slot ${prefix} nie ma pliku ani tokenu cache.`);
        }
        data.set(`slot_${prefix}`, file, file.name);
      }
      data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
    }
    for (const [prefix, photo] of state.loadedPhotos.entries()) {
      if (!state.files.has(prefix) && photo.dirty) {
        const transferSource = transferableSlotSource(prefix, photo);
        const token = transferablePhotoToken(photo, prefix);
        if (token) {
          data.set(`existing_slot_${prefix}`, token);
          data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
          changedPrefixes.add(prefix);
        } else if (transferSource === "ftp" && photo.ftp_filename) {
          data.set(`existing_ftp_slot_${prefix}`, photo.ftp_filename);
          data.set(
            `existing_ftp_ean_${prefix}`,
            photo.ean || state.loadedEntryOriginal?.ean || productForm.elements.ean.value
          );
          data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
          changedPrefixes.add(prefix);
        } else if (photo.dirty) {
          throw new Error(`Slot ${prefix} nie ma lokalnego ani FTP zrodla do przeniesienia.`);
        }
      }
    }
    for (const [prefix, item] of state.deletedSlots.entries()) {
      data.set(`delete_slot_${prefix}`, "1");
      if (item.token) data.set(`delete_local_slot_${prefix}`, item.token);
      if (item.ftp_filename) data.set(`delete_ftp_slot_${prefix}`, item.ftp_filename);
      if (item.sql) data.set(`delete_sql_slot_${prefix}`, "1");
    }
    startProcessStatusTicker(updateMode ? "Aktualizacja" : "Synchronizacja", changedPrefixes);
    const payload = await requestJson("/api/process", { method: "POST", body: data });
    stopProcessStatusTicker("Backend zakonczyl operacje. Odswiezanie widoku...");
    showResult(payload);
    const savedProductId = payload.entry?.product_id || productForm.elements.product_id.value;
    if (savedProductId) {
      productForm.elements.product_id.value = savedProductId;
    }
    state.loadedEntryOriginal = { ...formPayload(), product_id: savedProductId };
    updateFieldWarnings();
    state.deletedSlots.clear();
    clearSelectedFiles();
    setBusy(true, "Aktualizowanie listy wpisow...");
    upsertProductEntry(entryFromProcessPayload(payload, state.loadedEntryOriginal));
    if (payload.file_index) {
      state.fileIndex = payload.file_index;
    }
    renderDatalists();
    renderListEditor();
    updateRuntimeMetrics();
    for (const item of payload.saved_files || []) {
      if (item.prefix) changedPrefixes.add(item.prefix);
    }
    for (const item of payload.deleted_slots || []) {
      if (item.prefix) changedPrefixes.add(item.prefix);
    }
    for (const prefix of payload.migrated_slots || []) {
      if (prefix) changedPrefixes.add(prefix);
    }
    const entryToReload = {
      ...formPayload(),
      product_id: payload.entry?.product_id || productForm.elements.product_id.value,
    };
    clearFtpPreviewCacheForPrefixes(changedPrefixes, entryToReload.ean);
    clearSavedSlotMarkers(changedPrefixes);
    setBusy(true, "Odswiezanie podgladow zmienionych slotow...");
    if (identityChanged || !changedPrefixes.size) {
      await loadPhotosForEntry(entryToReload);
    } else {
      await loadPhotosForEntry(entryToReload, {
        prefixes: [...changedPrefixes],
        force: true,
        clearDirty: true,
      });
    }
    updateSubmitButtonState();
    setBusy(false, "Zakonczono.");
  } catch (error) {
    stopProcessStatusTicker();
    showError(error);
    setBusy(false, "");
  }
});

clearButton.addEventListener("click", () => {
  state.photoLoadRequestId += 1;
  productForm.reset();
  productForm.elements.product_id.value = "";
  for (const prefix of Array.from(state.filePreviewUrls.keys())) {
    revokeFilePreviewUrl(prefix);
  }
  state.files.clear();
  state.loadedPhotos.clear();
  state.slotFits.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
  state.userSelectedSlotSources.clear();
  state.photoSourceStatus.clear();
  state.ftpPreviewLoading.clear();
  state.ftpPreviewBackgroundLoading.clear();
  state.photoSourcesLoaded.clear();
  state.backgroundFtpLookupKey = "";
  state.backgroundFtpLookupRequestId += 1;
  window.clearTimeout(state.backgroundFtpLookupTimer);
  window.clearTimeout(state.backgroundFtpPreviewTimer);
  state.loadedEntryOriginal = null;
  state.lastAutoSearchKey = "";
  renderSlots();
  renderEntrySelect();
  updateFieldWarnings();
  clearResult();
  formStatus.textContent = "";
});

findByEanButton.addEventListener("click", () => {
  searchByEan().catch((error) => {
    formStatus.textContent = error.message;
  });
});

findProductButton.addEventListener("click", () => {
  searchByProduct().catch((error) => {
    formStatus.textContent = error.message;
  });
});

scanWebImagesButton?.addEventListener("click", () => {
  scanWebImages().catch((error) => {
    formStatus.textContent = error.message;
  });
});

webImagesButton?.addEventListener("click", () => {
  openWebImagesModal();
  renderWebImagesPicker();
});

webImageUrl?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  scanWebImages().catch((error) => {
    formStatus.textContent = error.message;
  });
});

for (const input of [
  webImageMinWidth,
  webImageMinHeight,
  webImageMinKb,
  webImageUrlFilter,
  webImageHideThumbnails,
]) {
  input?.addEventListener("input", renderWebImagesPicker);
  input?.addEventListener("change", renderWebImagesPicker);
}

if (webImageScanMode) {
  webImageScanMode.value = state.webImageScanMode;
}

webImageScanMode?.addEventListener("change", () => {
  state.webImageScanMode = webImageScanMode.value || "links";
  localStorage.setItem("picorg-web-image-scan-mode", state.webImageScanMode);
  renderWebImagesPicker();
});

browserExtensionHelpButton?.addEventListener("click", () => {
  if (!browserExtensionHelp) return;
  browserExtensionHelp.hidden = !browserExtensionHelp.hidden;
});

browserExtensionDownload?.addEventListener("click", () => {
  downloadBrowserExtension().catch((error) => {
    formStatus.textContent = error.message;
  });
});

browserExtensionReceiveButton?.addEventListener("click", () => {
  receiveBrowserExtensionImages().catch((error) => {
    formStatus.textContent = error.message;
  });
});

webImagesSelectVisibleButton?.addEventListener("click", () => {
  for (const entry of visibleWebImageEntries()) {
    state.webImageSelected.add(entry.index);
    queueWebImageCache(entry.image, "web", { render: false });
  }
  renderWebImagesPicker();
});

webImagesClearSelectionButton?.addEventListener("click", () => {
  state.webImageSelected.clear();
  renderWebImagesPicker();
});

webImagesClearDataButton?.addEventListener("click", () => {
  clearLoadedWebImages();
});

webImagesAddButton?.addEventListener("click", () => {
  addSelectedWebImagesToSlots().catch((error) => {
    formStatus.textContent = error.message;
  });
});

listAddForm.addEventListener("submit", (event) => {
  addListValue(event).catch((error) => {
    listStatus.textContent = error.message;
  });
});

listAddInput.addEventListener("input", () => {
  state.listFilter = listAddInput.value;
  renderListEditor();
  listAddInput.focus();
  const length = listAddInput.value.length;
  listAddInput.setSelectionRange(length, length);
});

logoutButton.addEventListener("click", async () => {
  if (!confirmPageExit()) {
    return;
  }
  state.navigationGuardBypass = true;
  await fetch("/api/logout", { method: "POST" }).catch(() => {});
  window.location.href = "/";
});

setupAutocomplete();
setupFieldChangeTracking();
setupPageExitGuards();
applyTheme();
loadBootstrap().catch(showError);
setInterval(() => {
  refreshFileIndexStatus().catch(() => {});
}, 5000);
setInterval(() => {
  pollLogStatus().catch(() => {});
}, 15000);
